import React from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'
import {GlobalContext} from 'reactstrap-toolbox'

import Logic from './logic'
import {statuses} from './logic/network'
import Login from './auth/Login'
import Logout from './auth/Logout'
import SwitchSession from './auth/SwitchSession'
import Navbar from './Navbar'
import {RoutesWithMenu, ErrorWithMenu} from './WithMenu'
import warnings from './warnings'


const Main = ({app_state}) => {
  if (app_state.error) {
    return <ErrorWithMenu error={app_state.error}/>
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
        <Route component={RoutesWithMenu}/>
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
    menu_open: false,
    disable_nav: false,
    conv_title: null,
    outdated: false,
  }

  componentDidMount () {
    warnings()
    // show this warnings to the user
    window.logic = new Logic(this.props.history)
    window.logic.add_listener('setState', s => this.setState(s))
    window.logic.add_listener('setError', e => this.setError(e))
  }

  componentDidUpdate (prevProps) {
    document.title = this.state.title || process.env.REACT_APP_NAME
    if (this.props.location !== prevProps.location) {
      this.state.error && this.setState({error: null})
      this.state.conv_title && this.setState({conv_title: null})
    }
    if (!this.state.user && this.state.conn_status && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    }
  }

  componentDidCatch (error, info) {
    // Raven.captureException(error, {extra: info})
    this.setState({error: error.toString()})
  }

  setError = error => {
    // Raven.captureMessage(`caught error: ${error.message || error.toString()}`, {
    //   stacktrace: true, level: 'warning', extra: error
    // })
    this.setState({error})
  }

  render () {
    const ctx = {
      setError: error => this.setError(error),
      setTitle: title => this.setState({title}),
      setConvTitle: conv_title => this.setState({conv_title}),
      setMenuItem: menu_item => this.setState({menu_item}),
      menu_item: this.state.menu_item,
      disable_nav: this.state.disable_nav,
      user: this.state.user,
      other_sessions: this.state.other_sessions,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar app_state={this.state} setAppState={s => this.setState(s)} location={this.props.location}/>
        <main className="container" id="main">
          <Main app_state={this.state}/>
        </main>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
