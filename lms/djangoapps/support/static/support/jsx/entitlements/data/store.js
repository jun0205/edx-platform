import { createStore, compose, applyMiddleware } from 'redux';
import thunkMiddleware from "redux-thunk"; 

import rootReducer from './reducers/index';

//create default data
const defaultState = {
	entitlements: [],
}

function configureStore(initialState){
  return createStore(
    rootReducer,
    initialState,
    applyMiddleware(thunkMiddleware),
  );
}

const store = configureStore(defaultState);

export default store;