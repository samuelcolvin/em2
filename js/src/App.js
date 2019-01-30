import React, {Component} from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'
import {library as FaLibrary} from '@fortawesome/fontawesome-svg-core'
import {far} from '@fortawesome/free-regular-svg-icons'
import {fas} from '@fortawesome/free-solid-svg-icons'
import {fab} from '@fortawesome/free-brands-svg-icons'

import {sleep} from './lib'
import {GlobalContext} from './lib/context'
import {conn_status} from './lib/requests'
import {Error, NotFound} from './lib/Errors'
import Worker from './run_worker'
import Navbar from './common/Navbar'
import Login from './auth/Login'
import ListConversations from './conversations/List'

// TODO replace with specific icons
FaLibrary.add(far, fas, fab)

const Routes = () => (
  <Switch>
    <Route exact path="/" component={ListConversations}/>

    <Route exact path="/login/" component={Login}/>

    <Route component={NotFound}/>
  </Switch>
)

const Main = ({state, ...props}) => {
  if (state.error) {
    return <Error error={state.error} location={props.location}/>
  } else if (state.connection_status === conn_status.not_connected && !state.user) {
    return (
      <div className="text-center">
        No internet connection and no local data, so sadly nothing much to show you. :-(
      </div>
    )
  } else {
    return <Routes/>
  }
}

class App extends Component {
  constructor (props) {
    super(props)
    this.state = {
      title: null,
      user: null,
      error: null,
      message: null,
      connection_status: null,
    }
    this.setMessage = this.setMessage.bind(this)
    this.setError = this.setError.bind(this)
    this.worker = new Worker(this)
  }

  async componentDidMount () {
    const user = await this.worker.call('authenticate')
    this.setState({user})
    if (!user && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
    }
  }

  componentDidUpdate (prevProps) {
    document.title = this.state.title ? `em2 - ${this.state.title}` : 'em2'
    if (this.props.location !== prevProps.location) {
      this.state.error && this.setState({error: null})
    }
  }

  async setMessage (message) {
    this.setState({message})
    await sleep(8000)
    this.setState({message: null})
  }

  componentDidCatch (error, info) {
    // Raven.captureException(error, {extra: info})
    this.setState({error: error.toString()})
  }

  setError (error) {
    if (error.status === 401 && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
      return
    }
    if (error.status === 0) {
      this.setState({connection_status: conn_status.not_connected})
      return
    }
    console.warn('setting error:', error)
    // Raven.captureMessage(`caught error: ${error.message || error.toString()}`, {
    //   stacktrace: true, level: 'warning', extra: error
    // })
    this.setState({error})
  }

  render () {
    const ctx = {
      setMessage: msg => this.setMessage(msg),
      setError: error => this.setError(error),
      setUser: user => this.setState({user}),
      setTitle: title => this.setState({title}),
      setConnectionStatus: connection_status => this.setState({connection_status}),
      user: this.state.user,
      worker: this.worker,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar app_state={this.state} location={this.props.location}/>
        <main className="container">
          <Main state={this.state} {...this.props}/>
        </main>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
