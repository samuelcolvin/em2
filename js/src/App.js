import React, {Component} from 'react'
import {Route, Switch, withRouter} from 'react-router-dom'

import {sleep} from './lib'
import {GlobalContext} from './lib/context'
import {Error, NotFound} from './lib/Errors'
import Navbar from './common/Navbar'
// import {Login} from './auth/Login'
import Worker from './run_worker'
import ListConversations from './conversations/List'

const Routes = () => (
  <Switch>
    <Route exact path="/" component={ListConversations}/>

    {/*<Route exact path="/login/" component={Login}/>*/}

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
    this.setMessage = this.setMessage.bind(this)
    this.setError = this.setError.bind(this)
    this.worker = new Worker(this)
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
    if (error.details && error.details.status === 401 && this.props.location.pathname !== '/login/') {
      this.props.history.push('/login/')
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
      user: this.state.user,
      worker: this.worker,
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
