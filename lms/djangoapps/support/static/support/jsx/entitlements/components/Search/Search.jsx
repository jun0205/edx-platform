import React from 'react';
import { InputText } from '@edx/paragon';


class Search extends React.Component{
	constructor(props) {
		super(props)
		this.state = { username: '' }
	}

	handleSubmit(event) {
		event.preventDefault(); //prevents the page from refreshing, refresh unneeded since state update will trigger react to update dom
		this.props.fetchEntitlements(this.state.username);
	}

	handleUserChange(event) {
		this.setState({ username: event });
	}

	render() {
		return (
			<form onSubmit={ this.handleSubmit.bind(this) }>
				<InputText 
					name="username"
		      label="Search by Username" 
		      value={ this.state.username } 
		      onChange={ this.handleUserChange.bind(this) }/>
				<input type="submit" hidden/>
			</form>
		);
	}
}


export default Search;