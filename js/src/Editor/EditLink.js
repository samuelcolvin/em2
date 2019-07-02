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

export default ({link, close, finished}) => {
  const [link_title, setTitle] = React.useState('')
  const [link_href, setHref] = React.useState('')
  const [href_error, setError] = React.useState(null)

  React.useEffect(() => {
    if (link && typeof(link) === 'string') {
      const href = as_url(link)
      if (href) {
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
            onChange={e => {setHref(e.target.value); setError(null)}}
          />
          <FormFeedback>{href_error}</FormFeedback>
        </FormGroup>
      </ModalBody>

      <ModalFooter>
        <ButtonGroup>
          <Button color="secondary" onClick={close}>Cancel</Button>
          {/*<Button color="warning" onClick={TODO}>Remove Link</Button>*/}
          <Button color="primary" onClick={save}>Save</Button>
        </ButtonGroup>
      </ModalFooter>
    </Modal>
  )
}

const http_re = /^https?:\/\//
const popular_tlds = '(com|edu|gov|org|co|info|net|ru|de|br|ir|uk|jp|it|io)'
const url_re = new RegExp(`(^www\\.|\\.${popular_tlds}$|\\.${popular_tlds}[/#?])`)

const as_url = s => {
  if (/ /.test(s)) {
    return null
  } else if (http_re.test(s)) {
    return encodeURI(s)
  } else if (url_re.test(s)) {
    return 'http://' + encodeURI(s)
  } else {
    return null
  }
}
