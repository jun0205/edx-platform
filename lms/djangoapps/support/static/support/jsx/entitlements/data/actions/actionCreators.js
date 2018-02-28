//increment
import * as clientApi from '../api/client';

export const entitlementActions = {
	fetch: {
		SUCCESS: 'FETCH_ENTITLEMENTS_SUCCESS',
		FAILURE: 'FETCH_ENTITLEMENTS_FAILURE'
	}
}

const fetchEntitlements = username => {
  return dispatch => {
    clientApi.getEntitlements(username)
    .then( response => {
      if (response.ok) {
        return response.json();
      }
      throw new Error(response);
    })
    .then(
      json => dispatch(fetchEntitlementsSuccess(json)),
      error => dispatch(fetchEntitlementsFailure(error))
    )
  }
}
	
const fetchEntitlementsSuccess = entitlements => ({
	type: entitlementActions.fetch.SUCCESS,
	entitlements
})

const fetchEntitlementsFailure = error => ({
	type: entitlementActions.fetch.FAILURE,
	error
})

export {
	fetchEntitlements,
	fetchEntitlementsSuccess,
	fetchEntitlementsFailure,
}