import React, {Component} from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'

import {sleep} from './lib'
import {GlobalContext} from './lib/context'
import request from './lib/requests'
import {Error, NotFound} from './lib/Errors'
import Navbar from './common/Navbar'
// import {Login, AcceptOauth} from './auth/Login'
// import Main from './stream'
// import {EndpointList, EndpointDetails} from './bread/Endpoints'
import Worker from './run_worker'
import List from './list'

const Routes = () => (
    <Switch>
      <Route exact path="/" component={List}/>

      {/*<Route exact path="/login/" component={Login}/>*/}
      {/*<Route exact path="/oauth/gh/" component={AcceptOauth}/>*/}

      <Route component={NotFound}/>
    </Switch>
)

class App extends Component {
  constructor (props) {
    super(props)
    this.state = {
      title: null,
      user: null,
      error: null,
      message: null,
      status: null,
    }
    this.authenticate = this.authenticate.bind(this)
    this.setMessage = this.setMessage.bind(this)
    this.setError = this.setError.bind(this)
    this.setUser = this.setUser.bind(this)
    this.requests = {
      get: (path, config) => request(this, 'GET', path, config),
      post: (path, data, config) => {
        config = config || {}
        config.send_data = data
        return request(this, 'POST', path, config)
      }
    }
    this.worker = new Worker(this)
  }

  async componentDidMount () {
    // console.log(await this.worker.fetch('testing', 11))
    // this.authenticate()
  }

  componentDidUpdate (prevProps) {
    document.title = this.state.title ? `em2 - ${this.state.title}` : 'em2'
    if (this.props.location !== prevProps.location) {
      this.state.error && this.setState({error: null})
      // this.authenticate()
    }
  }

  async authenticate () {
    if (this.state.user || ['/login/', '/oauth/gh/'].includes(this.props.location.pathname)) {
      return
    }
    const r = await this.requests.get('/user/', {expected_status: [200, 401]})
    if (r.status === 200) {
      this.setUser(r.data)
    } else {
      this.setMessage({icon: 'sign-in-alt', message: 'Login Required'})
      this.props.history.push('/login/')
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
    console.warn('setting error:', error)
    // Raven.captureMessage(`caught error: ${error.message || error.toString()}`, {
    //   stacktrace: true, level: 'warning', extra: error
    // })
    this.setState({error})
  }

  setUser (user) {
    this.setState({user})
  }

  render () {
    const ctx = {
      setMessage: msg => this.setMessage(msg),
      setError: error => this.setError(error),
      setUser: user => this.setUser(user),
      user: this.state.user,
      requests: this.requests,
      // worker: this.worker,
    }
    return (
      <GlobalContext.Provider value={ctx}>
        <Navbar {...this.props.state} location={this.props.location}/>
        <main className="container">
          {this.state.error ?
            <Error error={this.state.error} location={this.props.location}/>
            :
            <Routes/>
          }
        </main>
      </GlobalContext.Provider>
    )
  }
}

export default withRouter(App)
