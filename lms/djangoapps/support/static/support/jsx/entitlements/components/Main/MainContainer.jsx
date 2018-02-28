import {bindActionCreators} from 'redux';
import {connect} from 'react-redux';
import * as actionCreators from '../../data/actions/actionCreators';
import Main from './Main';

function mapStateToProps(state) {
	return {
		entitlements: state.entitlements,
		modal: state.modal
	};
}

function mapDispatchToProps(dispatch) {
	return bindActionCreators(actionCreators, dispatch);
}

const MainContainer = connect(
	mapStateToProps,
	mapDispatchToProps
)(Main);



export default MainContainer;