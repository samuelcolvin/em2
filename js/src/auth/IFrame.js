import React from 'react'

const iframe_csp = [
  `default-src 'none'`,
  `script-src 'sha256-f6NVIWP0rMwAsNc3XtxZkAnIWv2iH4ZWlJCvTFbZdFQ='`,
  `style-src ${window.location.origin} https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/`,
]

let login_url
if (process.env.NODE_ENV === 'development') {
  login_url = 'http://localhost:8000/auth/login/'
  iframe_csp.push(`connect-src ${window.location.origin} http://localhost:8000`)
} else {
  login_url = `https://auth.${process.env.REACT_APP_DOMAIN}/login/`
}

const iframe_src_base64 = btoa(`
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <title>Login Form</title>
    <meta http-equiv="Content-Security-Policy" content="${iframe_csp.join(';')}">
    <link rel="stylesheet" crossorigin="anonymous" \
      integrity="sha256-YLGeXaapI0/5IgZopewRJcFXomhRMlYYjugPLSyNjTY=" \
      href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/4.3.1/css/bootstrap.min.css">
    <link rel="stylesheet" href="${origin}/iframes/styles.css">
  </head>
  <body class="pt-2 px-1">
    <form id="login-form" action="${login_url}" method="POST" data-origin="${window.location.origin}">

      <small class="error mb-2" id="user-error"></small>

      <div class="form-item">
        <input type="email" id="email" class="form-control" placeholder="Email address" required autofocus>
        <label for="email">Email address</label>
      </div>

      <div class="form-item">
        <input type="password" id="password" class="form-control" placeholder="Password"
               minlength="6" maxlength="100" required>
        <label for="password">Password</label>
      </div>

      <button class="btn btn-lg btn-primary btn-block" type="submit">Log in</button>
    </form>
    <script>
      const form = document.getElementById('login-form')
      const user_error = document.getElementById('user-error')
      const origin = form.getAttribute('data-origin')
      const email_el = document.getElementById('email')
      const password_el = document.getElementById('password')

      function on_error (message, status, xhr, error) {
        console.warn('Error:', message, xhr, error, form)
        const error_details = {
          message,
          details: {
            error, origin, status, xhr_response: xhr.responseText,
            method: form.method, action: form.action
          },
        }
        window.parent.postMessage({error: error_details}, origin)
      }

      let grecaptcha_token = null
      let grecaptcha_required = false
      window.addEventListener('message', event => {
        if (event.origin === origin && event.data.grecaptcha_token) {
          grecaptcha_token = data.grecaptcha_token
          user_error.innerText = ''
        }
      }, false)

      // check if we're connected and whether grecaptcha is required
      const xhr = new XMLHttpRequest()
      xhr.open('GET', form.action)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.onload = () => {
        let data
        try {
          data = JSON.parse(xhr.responseText)
        } catch (error) {
          on_error('Error decoding response', xhr.status, xhr, error)
        }
        if (xhr.status === 200) {
          grecaptcha_required = data.grecaptcha_required
          window.parent.postMessage({grecaptcha_required}, origin)
        } else {
          on_error(data.message || 'Unexpected response', xhr.status, xhr)
        }
      }
      xhr.onerror = e => on_error('Network Error', 0, xhr, e)
      xhr.send()

      function on_submit (e) {
        e.preventDefault()
        email_el.readOnly = true
        password_el.readOnly = true
        user_error.innerText = ''

        if (grecaptcha_required && !grecaptcha_token) {
          email_el.readOnly = false
          password_el.readOnly = false
          user_error.innerText = 'Captcha required.'
          return
        }

        const post_data = JSON.stringify({
          email: email_el.value,
          password: password_el.value,
          grecaptcha_token,
        })
        grecaptcha_token = null

        const xhr = new XMLHttpRequest()
        xhr.open(form.method, form.action)
        xhr.setRequestHeader('Accept', 'application/json')
        xhr.setRequestHeader('Content-Type', 'application/json')
        xhr.onload = () => {
          let data
          try {
            data = JSON.parse(xhr.responseText)
          } catch (error) {
            on_error('Error decoding response', xhr.status, xhr, error)
          }
          if (xhr.status === 470) {
            user_error.innerText = 'Email address or password incorrect.'
            email_el.readOnly = false
            password_el.readOnly = false
            password_el.value = ''
            grecaptcha_required = data.details.grecaptcha_required
            if (data.details.grecaptcha_required) {
              window.parent.postMessage({grecaptcha_required}, origin)
            }
          } else if (xhr.status === 200) {
            window.parent.postMessage(data, origin)
          } else {
            on_error(data.message || 'Unexpected response', xhr.status, xhr)
          }
        }
        xhr.onerror = e => on_error('Network Error', 0, xhr, e)
        xhr.send(post_data)
      }
      form.addEventListener('submit', on_submit, true)
    </script>
  </body>
</html>
`)

export default class IFrame extends React.Component {
  shouldComponentUpdate (nextProps) {
    return false
  }

  render () {
    return (
      <div className="iframe-container">
        <div className="zero-height d-flex justify-content-center">
          Loading...
        </div>
        <iframe
            ref={this.props.iframe_ref}
            title="Login"
            frameBorder="0"
            scrolling="no"
            sandbox="allow-forms allow-scripts"
            src={`data:text/html;base64,${iframe_src_base64}`}
        />
      </div>
    )
  }
}
