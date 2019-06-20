import React from 'react'
import ReactDOM from 'react-dom'
import {BrowserRouter as Router} from 'react-router-dom'
import './styles/main.scss'
import App from './App'
import register_service_worker from './service_worker'

ReactDOM.render(<Router><App/></Router>, document.getElementById('root'))
register_service_worker()

if (process.env.NODE_ENV === 'development') {
  // em2/main.py restart_react_dev_server, hack to prompt reload on python code change
  import('./.update.js')
}
