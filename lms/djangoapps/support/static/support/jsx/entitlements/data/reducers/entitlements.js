import { entitlementActions } from '../actions/actionCreators';

function entitlements(state = [], action){
  switch(action.type){
    case entitlementActions.fetch.SUCCESS:
      //TO BE REMOVED when entitlements in store are displayed in table
      console.log('Fetching entitlements success ', action.entitlements)
      return action.entitlements
    case entitlementActions.fetch.FAILURE:
      console.log('Fetching entitlements failed ', action.error)
      return state
    default:
      return state;
	}
}

export default entitlements;