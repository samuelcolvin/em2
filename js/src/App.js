import React from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'
import {GlobalContext, Error} from 'reactstrap-toolbox'

import Logic from './logic'
import {statuses} from './utils/network'
import Login from './auth/Login'
import Logout from './auth/Logout'
import SwitchSession from './auth/SwitchSession'
import Navbar from './Navbar'
import WithMenu from './WithMenu'


const Main = ({app_state}) => {
  if (app_state.error) {
    return <Error error={app_state.error}/>
  } else if (!app_state.conn_status) {
    // this should happen very briefly, don't show loading to avoid FOUC
    return null
  } else if (app_state.conn_status === statuses.offline && !app_state.user) {
    return (
      <div className="text-center">
        No internet connection and no local data, so sadly nothing much to show you. :-(
      </div>
    )
  } else {
    return (
      <Switch>
        <Route exact path="/login/" component={Login}/>
        <Route exact path="/logout/" component={Logout}/>
        <Route exact path="/switch/:id(\d+)/" component={SwitchSession}/>
        <Route component={WithMenu}/>
      </Switch>
    )
  }
}

class App extends React.Component {
  state = {
    title: null,
    error: null,
    user: null,
    other_sessions: [],
    conn_status: null,
    menu_item: null,
  }

  componentDidMount () {
    window.logic = new Logic(this.props.history)
    window.logic.add_listener('setState', s => this.setState(s))
    window.logic.add_listener('setUser', u => this.setUser(u))
  }

  componentDidUpdate (prevProps) {
    document.title = this.state.title ? this.state.title : 'em2'
    if (this.props.location !== prevProps.location) {
      this.state.error && this.setState({error: null})
    }
    if (!this.state.user && this.state.conn_status && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    }
  }

  setUser = user => {
    this.setState({user})
    sessionStorage['session_id'] = JSON.stringify(user ? user.session_id : null)
  }

  componentDidCatch (error, info) {
    // Raven.captureException(error, {extra: info})
    this.setState({error: error.toString()})
  }

  setError = error => {
    if (error.status === 401 && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    } else {
      console.warn('setting error:', error)
      // Raven.captureMessage(`caught error: ${error.message || error.toString()}`, {
      //   stacktrace: true, level: 'warning', extra: error
      // })
      this.setState({error})
    }
  }

  render () {
    const ctx = {
      setError: error => this.setError(error),
      setTitle: title => this.setState({title}),
      setMenuItem: menu_item => this.setState({menu_item}),
      menu_item: this.state.menu_item,
      user: this.state.user,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar app_state={this.state} location={this.props.location}/>
        <main className="container" id="main">
          <Main app_state={this.state}/>
        </main>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
