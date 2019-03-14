import React from 'react'
import ReactDOM from 'react-dom'
import {BrowserRouter as Router} from 'react-router-dom'
import './styles/main.scss'
import App from './App'
import * as serviceWorker from './serviceWorker'

ReactDOM.render(<Router><App/></Router>, document.getElementById('root'))
serviceWorker.register()

if (process.env.NODE_ENV === 'development') {
  // em2/main.py restart_react_dev_server, hack to prompt reload on python code change
  import('./.update.js')
}
