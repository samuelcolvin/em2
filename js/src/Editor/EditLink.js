import React from 'react'
import {
  Input,
  Button,
  ButtonGroup,
  Label,
  FormGroup,
  FormFeedback,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from 'reactstrap'
import isUrl from 'is-url'
import {on_backspace, on_enter, on_space} from './utils'

export const EditLink = ({link, close, finished}) => {
  const [link_title, setTitle] = React.useState('')
  const [link_href, setHref] = React.useState('')
  const [href_error, setError] = React.useState(null)

  React.useEffect(() => {
    // using ids here seems to work better than refs
    let focus_id = 'link-href'
    if (link && typeof(link) === 'string') {
      const href = as_url(link)
      if (href) {
        focus_id = 'link-title'
        setHref(href)
        setTitle(link)
      } else {
        setTitle(link)
        setHref('')
      }
    } else if (link && typeof(link) === 'object') {
      setTitle(link.title)
      setHref(link.href)
    } else {
      setTitle('')
      setHref('')
    }
    setTimeout(() => {
      const el = document.getElementById(focus_id)
      el && el.focus()
    }, 0)
  }, [link])

  const save = () => {
    if (isUrl(link_href)) {
      setError(null)
      finished(link_title || link_href, link_href)
    } else if (link_href) {
      setError('Invalid URL, make sure you enter a full URL starting with http(s)://.')
    } else (
      setError('URL may not be be blank.')
    )
  }

  const onKeyDown = e => {
    if (e.key === 'Enter') {
      e.preventDefault()
      save()
    }
  }

  return (
    <Modal isOpen={link !== null} toggle={close} className="simplified-modal">
      <ModalHeader toggle={close}>Edit Link</ModalHeader>
      <ModalBody>
         <FormGroup>
          <Label for="link-title">Link Title</Label>
          <Input
            id="link-title"
            type="text"
            value={link_title}
            onChange={e => setTitle(e.target.value)}
          />
        </FormGroup>

         <FormGroup>
          <Label for="link-href">Link URL</Label>
          <Input
            id="link-href"
            type="text"
            invalid={!!href_error}
            value={link_href}
            onKeyDown={onKeyDown}
            onChange={e => {setHref(e.target.value); setError(null)}}
          />
          <FormFeedback>{href_error}</FormFeedback>
        </FormGroup>
      </ModalBody>

      <ModalFooter>
        <ButtonGroup>
          <Button color="secondary" onClick={close}>Cancel</Button>
          <Button color="primary" onClick={save}>Save</Button>
        </ButtonGroup>
      </ModalFooter>
    </Modal>
  )
}

const http_re = /^https?:\/\//
const popular_tlds = '(com|edu|gov|org|co|info|net|ru|de|br|ir|uk|jp|it|io)'
const url_like_re = new RegExp(`(^www\\.|\\.${popular_tlds}$|\\.${popular_tlds}[/#?])`)

export const as_url = s => {
  // could use something like /[^a-zA-Z0-9.:\/?=%_\-]/ here, but may this is better
  if (/[ '"]/.test(s)) {
    return null
  } else if (http_re.test(s)) {
    return encodeURI(s)
  } else if (url_like_re.test(s)) {
    return 'http://' + encodeURI(s)
  } else {
    return null
  }
}
