"""Entitlement Models"""

import logging
import uuid as uuid_tools
from datetime import timedelta

from django.conf import settings
from django.contrib.sites.models import Site
from django.db import models
from django.db import transaction
from django.utils.timezone import now
from model_utils.models import TimeStampedModel

from lms.djangoapps.certificates.models import GeneratedCertificate
from openedx.core.djangoapps.catalog.utils import get_course_uuid_for_course
from openedx.core.djangoapps.content.course_overviews.models import CourseOverview
from student.models import CourseEnrollment
from student.models import CourseEnrollmentException
from util.date_utils import strftime_localized
from entitlements.utils import is_course_run_entitlement_fulfillable

log = logging.getLogger("common.entitlements.models")


class CourseEntitlementPolicy(models.Model):
    """
    Represents the Entitlement's policy for expiration, refunds, and regaining a used certificate
    """

    DEFAULT_EXPIRATION_PERIOD_DAYS = 450
    DEFAULT_REFUND_PERIOD_DAYS = 60
    DEFAULT_REGAIN_PERIOD_DAYS = 14

    # Use a DurationField to calculate time as it returns a timedelta, useful in performing operations with datetimes
    expiration_period = models.DurationField(
        default=timedelta(days=DEFAULT_EXPIRATION_PERIOD_DAYS),
        help_text="Duration in days from when an entitlement is created until when it is expired.",
        null=False
    )
    refund_period = models.DurationField(
        default=timedelta(days=DEFAULT_REFUND_PERIOD_DAYS),
        help_text="Duration in days from when an entitlement is created until when it is no longer refundable",
        null=False
    )
    regain_period = models.DurationField(
        default=timedelta(days=DEFAULT_REGAIN_PERIOD_DAYS),
        help_text=("Duration in days from when an entitlement is redeemed for a course run until "
                   "it is no longer able to be regained by a user."),
        null=False
    )
    site = models.ForeignKey(Site)

    def get_days_until_expiration(self, entitlement):
        """
        Returns an integer of number of days until the entitlement expires.
        Includes the logic for regaining an entitlement.
        """
        now_timestamp = now()
        expiry_date = entitlement.created + self.expiration_period
        days_until_expiry = (expiry_date - now_timestamp).days
        if not entitlement.enrollment_course_run:
            return days_until_expiry
        course_overview = CourseOverview.get_from_id(entitlement.enrollment_course_run.course_id)
        # Compute the days left for the regain
        days_since_course_start = (now_timestamp - course_overview.start).days
        days_since_enrollment = (now_timestamp - entitlement.enrollment_course_run.created).days
        days_since_entitlement_created = (now_timestamp - entitlement.created).days

        # We want to return whichever days value is less since it is then the more recent one
        days_until_regain_ends = (self.regain_period.days -  # pylint: disable=no-member
                                  min(days_since_course_start, days_since_enrollment, days_since_entitlement_created))

        # If the base days until expiration is less than the days until the regain period ends, use that instead
        if days_until_expiry < days_until_regain_ends:
            return days_until_expiry

        return days_until_regain_ends  # pylint: disable=no-member

    def is_entitlement_regainable(self, entitlement):
        """
        Determines from the policy if an entitlement can still be regained by the user, if they choose
        to by leaving and regaining their entitlement within policy.regain_period days from start date of
        the course or their redemption, whichever comes later, and the expiration period hasn't passed yet
        """
        if entitlement.expired_at:
            return False

        if entitlement.enrollment_course_run:
            if GeneratedCertificate.certificate_for_student(
                    entitlement.user_id, entitlement.enrollment_course_run.course_id) is not None:
                return False

            # This is >= because a days_until_expiration 0 means that the expiration day has not fully passed yet
            # and that the entitlement should not be expired as there is still time
            return self.get_days_until_expiration(entitlement) >= 0
        return False

    def is_entitlement_refundable(self, entitlement):
        """
        Determines from the policy if an entitlement can still be refunded, if the entitlement has not
        yet been redeemed (enrollment_course_run is NULL) and policy.refund_period has not yet passed, or if
        the entitlement has been redeemed, but the regain period hasn't passed yet.
        """
        # If the Entitlement is expired already it is not refundable
        if entitlement.expired_at:
            return False

        # If there's no order number, it cannot be refunded
        if entitlement.order_number is None:
            return False

        # This is > because a get_days_since_created of refund_period means that that many days have passed,
        # which should then make the entitlement no longer refundable
        if entitlement.get_days_since_created() > self.refund_period.days:  # pylint: disable=no-member
            return False

        if entitlement.enrollment_course_run:
            return self.is_entitlement_regainable(entitlement)

        return True

    def is_entitlement_redeemable(self, entitlement):
        """
        Determines from the policy if an entitlement can be redeemed, if it has not passed the
        expiration period of policy.expiration_period, and has not already been redeemed
        """
        # This is < because a get_days_since_created of expiration_period means that that many days have passed,
        # which should then expire the entitlement
        return (entitlement.get_days_since_created() < self.expiration_period.days  # pylint: disable=no-member
                and not entitlement.enrollment_course_run
                and not entitlement.expired_at)

    def __unicode__(self):
        return u'Course Entitlement Policy: expiration_period: {}, refund_period: {}, regain_period: {}'\
            .format(
                self.expiration_period,
                self.refund_period,
                self.regain_period,
            )


class CourseEntitlement(TimeStampedModel):
    """
    Represents a Student's Entitlement to a Course Run for a given Course.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    uuid = models.UUIDField(default=uuid_tools.uuid4, editable=False, unique=True)
    course_uuid = models.UUIDField(help_text='UUID for the Course, not the Course Run')
    expired_at = models.DateTimeField(
        null=True,
        help_text='The date that an entitlement expired, if NULL the entitlement has not expired.',
        blank=True
    )
    mode = models.CharField(max_length=100, help_text='The mode of the Course that will be applied on enroll.')
    enrollment_course_run = models.ForeignKey(
        'student.CourseEnrollment',
        null=True,
        help_text='The current Course enrollment for this entitlement. If NULL the Learner has not enrolled.',
        blank=True
    )
    order_number = models.CharField(max_length=128, null=True)
    _policy = models.ForeignKey(CourseEntitlementPolicy, null=True, blank=True)

    @property
    def expired_at_datetime(self):
        """
        Getter to be used instead of expired_at because of the conditional check and update
        """
        self.update_expired_at()
        return self.expired_at

    @expired_at_datetime.setter
    def expired_at_datetime(self, value):
        """
        Setter to be used instead for expired_at for consistency
        """
        self.expired_at = value

    @property
    def policy(self):
        """
        Getter to be used instead of _policy because of the null object pattern
        """
        return self._policy or CourseEntitlementPolicy()

    @policy.setter
    def policy(self, value):
        """
        Setter to be used instead of _policy because of the null object pattern
        """
        self._policy = value

    def get_days_since_created(self):
        """
        Returns an integer of number of days since the entitlement has been created
        """
        return (now() - self.created).days

    def update_expired_at(self):
        """
        Updates the expired_at attribute if it is not set AND it is expired according to the entitlement's policy,
        OR if the policy can no longer be regained AND the policy has been redeemed
        """
        if not self.expired_at:
            if (self.policy.get_days_until_expiration(self) < 0 or
                    (self.enrollment_course_run and not self.is_entitlement_regainable())):
                self.expired_at = now()
                self.save()

    def get_days_until_expiration(self):
        """
        Returns an integer of number of days until the entitlement expires based on the entitlement's policy
        """
        return self.policy.get_days_until_expiration(self)

    def is_entitlement_regainable(self):
        """
        Returns a boolean as to whether or not the entitlement can be regained based on the entitlement's policy
        """
        return self.policy.is_entitlement_regainable(self)

    def is_entitlement_refundable(self):
        """
        Returns a boolean as to whether or not the entitlement can be refunded based on the entitlement's policy
        """
        return self.policy.is_entitlement_refundable(self)

    def is_entitlement_redeemable(self):
        """
        Returns a boolean as to whether or not the entitlement can be redeemed based on the entitlement's policy
        """
        return self.policy.is_entitlement_redeemable(self)

    def to_dict(self):
        """
        Convert entitlement to dictionary representation including relevant policy information.

        Returns:
            The entitlement UUID
            The associated course's UUID
            The date at which the entitlement expired. None if it is still active.
            The localized string representing the date at which the entitlement expires.
        """
        expiration_date = None
        if self.get_days_until_expiration() < settings.ENTITLEMENT_EXPIRED_ALERT_PERIOD:
            expiration_date = strftime_localized(
                now() + timedelta(days=self.get_days_until_expiration()),
                'SHORT_DATE'
            )
        expired_at = strftime_localized(self.expired_at_datetime, 'SHORT_DATE') if self.expired_at_datetime else None

        return {
            'uuid': str(self.uuid),
            'course_uuid': str(self.course_uuid),
            'expired_at': expired_at,
            'expiration_date': expiration_date
        }

    def set_enrollment(self, enrollment):
        """
        Fulfills an entitlement by specifying a session.
        """
        self.enrollment_course_run = enrollment
        self.save()

    @classmethod
    def unexpired_entitlements_for_user(cls, user):
        return cls.objects.filter(user=user, expired_at=None).select_related('user')

    @classmethod
    def get_entitlement_if_active(cls, user, course_uuid):
        """
        Retrieves the active entitlement for the course_uuid and User.

        An active entitlement is defined as an entitlement that has not yet expired or has a currently enrolled session.
        If there is more than one entitlement, return the most recently created active entitlement.

        Arguments:
            user: User that owns the Course Entitlement
            course_uuid: The Course UUID for a Course that we are retrieving active entitlements for.

        Returns:
            CourseEntitlement: Returns the most recently created entitlement for a given course uuid if an
                               active entitlement exists, otherwise returns None
        """
        try:
            return cls.objects.filter(
                user=user,
                course_uuid=course_uuid
            ).exclude(
                expired_at__isnull=False,
                enrollment_course_run=None
            ).latest('created')
        except CourseEntitlement.DoesNotExist:
            return None

    @classmethod
    def get_active_entitlements_for_user(cls, user):
        """
        Returns a list of active (enrolled or not yet expired) entitlements.

        Returns any entitlements that are:
            1) Not expired and no session selected
            2) Not expired and a session is selected
            3) Expired and a session is selected

        Does not return any entitlements that are:
            1) Expired and no session selected
        """
        return cls.objects.filter(user=user).exclude(
            expired_at__isnull=False,
            enrollment_course_run=None
        ).select_related('user').select_related('enrollment_course_run')

    @classmethod
    def get_fulfillable_entitlements(cls, user):
        """
        Returns all fulfillable entitlements for a User

        Arguments:
            user (User): The user we are looking at the entitlements of.

        Returns
            Queryset: A queryset of course Entitlements ordered descending by creation date that a user can enroll in.
            These must not be expired and not have a course run already assigned to it.
        """

        return cls.objects.filter(
            user=user,
        ).exclude(
            expired_at__isnull=False,
            enrollment_course_run__isnull=False
        ).order_by('-created')

    @classmethod
    def get_fulfillable_entitlement_for_user_course_run(cls, user, course_run_key):
        """
        Retrieves a fulfillable entitlement for the user and the given course run.

        Arguments:
            user (User): The user that we are inspecting the entitlements for.
            course_run_key (CourseKey): The course run Key.

        Returns:
            CourseEntitlement: The most recent fulfillable CourseEntitlement, None otherwise.
        """
        # Check if the User has any fulfillable entitlements.
        # Note: Wait to retrieve the Course UUID until we have confirmed the User has fulfillable entitlements.
        # This was done to avoid calling the APIs when the User does not have an entitlement.
        entitlements = cls.get_fulfillable_entitlements(user)
        if entitlements:
            course_uuid = get_course_uuid_for_course(course_run_key)
            if course_uuid:
                entitlement = entitlements.filter(course_uuid=course_uuid).first()
                if (is_course_run_entitlement_fulfillable(course_run_key=course_run_key, entitlement=entitlement) and
                        entitlement.is_entitlement_redeemable()):
                    return entitlement
        return None

    @classmethod
    @transaction.atomic
    def enroll_user_and_fulfill_entitlement(cls, entitlement, course_run_key):
        """
        Enrolls the user in the Course Run and updates the entitlement with the new Enrollment.

        Returns:
            bool: True if successfully fulfills given entitlement by enrolling the user in the given course run.
        """
        try:
            enrollment = CourseEnrollment.enroll(
                user=entitlement.user,
                course_key=course_run_key,
                mode=entitlement.mode
            )
        except CourseEnrollmentException:
            log.exception('Login for Course Entitlement {uuid} failed'.format(uuid=entitlement.uuid))
            return False

        entitlement.set_enrollment(enrollment)
        return True

    @classmethod
    def check_for_existing_entitlement_and_enroll(cls, user, course_run_key):
        """
        Looks at the User's existing entitlements to see if the user already has a Course Entitlement for the
        course run provided in the course_key.  If the user does have an Entitlement with no run set, the User is
        enrolled in the mode set in the Entitlement.

        Arguments:
            user (User): The user that we are inspecting the entitlements for.
            course_run_key (CourseKey): The course run Key.
        Returns:
            bool: True if the user had an eligible course entitlement to which an enrollment in the
            given course run was applied.
        """
        entitlement = cls.get_fulfillable_entitlement_for_user_course_run(user, course_run_key)
        if entitlement:
            return cls.enroll_user_and_fulfill_entitlement(entitlement, course_run_key)
        return False


class CourseEntitlementSupportDetail(TimeStampedModel):
    """
    Table recording support interactions with an entitlement
    """
    # Reasons deprecated
    LEAVE_SESSION = 'LEAVE'
    CHANGE_SESSION = 'CHANGE'
    LEARNER_REQUEST_NEW = 'LEARNER_NEW'
    COURSE_TEAM_REQUEST_NEW = 'COURSE_TEAM_NEW'
    OTHER = 'OTHER'
    ENTITLEMENT_SUPPORT_REASONS = (
        (LEAVE_SESSION, u'Learner requested leave session for expired entitlement'),
        (CHANGE_SESSION, u'Learner requested session change for expired entitlement'),
        (LEARNER_REQUEST_NEW, u'Learner requested new entitlement'),
        (COURSE_TEAM_REQUEST_NEW, u'Course team requested entitlement for learnerg'),
        (OTHER, u'Other'),
    )

    REISSUE = 'REISSUE'
    CREATE = 'CREATE'
    ENTITLEMENT_SUPPORT_ACTIONS = (
        (REISSUE, 'Re-issue entitlement'),
        (CREATE, 'Create new entitlement'),
    )

    entitlement = models.ForeignKey('entitlements.CourseEntitlement')
    support_user = models.ForeignKey(settings.AUTH_USER_MODEL)

    #Deprecated: use action instead.
    reason = models.CharField(max_length=15, choices=ENTITLEMENT_SUPPORT_REASONS)
    action = models.CharField(max_length=15, choices=ENTITLEMENT_SUPPORT_ACTIONS)

    comments = models.TextField(null=True)

    unenrolled_run = models.ForeignKey(
        CourseOverview,
        null=True,
        blank=True,
        db_constraint=False,
    )

    def __unicode__(self):
        """Unicode representation of an Entitlement"""
        return u'Course Entitlement Support Detail: entitlement: {}, support_user: {}, reason: {}'.format(
            self.entitlement,
            self.support_user,
            self.reason,
        )

    @classmethod
    def get_support_actions_list(cls):
        """
        Method for retrieving a serializable version of the entitlement support reasons

        Returns
            list: Containing the possible support actions
        """
        return [
            action[0]  # get just the action code, not the human readable description.
            for action
            in cls.ENTITLEMENT_SUPPORT_ACTIONS
        ]
