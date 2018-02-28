import React from 'react';

import { Provider } from 'react-redux';
import store from './data/store';

import MainContainer from './components/Main/MainContainer';

export function EntitlementSupportPage(props) {
  return (
    <Provider store={ store }>
      <MainContainer { ...props }/>
    </Provider>
  );
}
