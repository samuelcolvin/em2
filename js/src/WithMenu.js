import React from 'react'
import {Link, Route, Switch} from 'react-router-dom'
import {Row, Col, ListGroup, ListGroupItem as BsListGroupItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {NotFound, WithContext, as_title} from 'reactstrap-toolbox'
import ListConversations from './conversations/List'
import ConversationDetails from './conversations/Details'
import CreateConversation from './conversations/Create'

const ListGroupItem = ({to, active, icon, title, count, count_unseen}) => (
  <BsListGroupItem tag={Link} to={to} action active={active}>
    <div className="d-flex justify-content-between">
      <div>
        <FontAwesomeIcon icon={icon} className="w-20 mr-1"/> {title}
      </div>
      <div>
        {count_unseen ? (
          <span className={'badge mr-2 badge-' + (active ? 'dark': 'primary')}>
            {count_unseen}
          </span>
        ): null}
        {Number.isInteger(count) ? (
          <span className={'badge badge-' + (active ? 'light': 'secondary')}>
            {count}
          </span>
        ): null}
      </div>
    </div>
  </BsListGroupItem>
)

const main_menu_items = [
  {to: '/', name: 'inbox', unseen: true, icon: fas.faInbox},
  {to: '/draft/', name: 'draft', icon: fas.faFileAlt},
  {to: '/sent/', name: 'sent', icon: fas.faPaperPlane},
  {to: '/archive/', name: 'archive', icon: fas.faArchive},
  // {to: '/all/', name: 'all', icon: fas.faGlobe},
  {to: '/deleted/', name: 'deleted', icon: fas.faTrash},
  {to: '/spam/', name: 'spam', icon: fas.faRadiation},
]

class LeftMenu_ extends React.Component {
  state = {flags: {}}

  componentDidMount () {
    this.mounted = true
    this.update()
    this.remove_listener = this.props.ctx.worker.add_listener('flag-change', this.update)
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener && this.remove_listener()
  }

  update = async () => {
    if (this.mounted) {
      const r = await this.props.ctx.worker.call('conv-counts')
      this.setState({flags: r.flags, labels: r.labels})
    }
  }

  render () {
    const s = this.props.ctx.menu_item
    return (
      <div className="left-menu">
        <div className="box no-pad">
          <ListGroup>
            <ListGroupItem
              to="/create/"
              active={s === 'create'}
              icon={fas.faKeyboard}
              title="Compose"
            />
          </ListGroup>
        </div>

        <div className="box no-pad">
          <ListGroup>
            {main_menu_items.map(m => (
              <ListGroupItem
                key={m.to}
                to={m.to}
                active={this.props.ctx.menu_item === m.name}
                icon={m.icon}
                title={as_title(m.name)}
                count={this.state.flags[m.name]}
                count_unseen={m.unseen && this.state.flags['unseen']}
              />
            ))}
          </ListGroup>
        </div>

        <div className="box no-pad">
          <ListGroup>
            <ListGroupItem
              to="/settings/"
              active={this.props.ctx.menu_item === 'settings'}
              icon={fas.faCog}
              title="Settings"
            />
          </ListGroup>
        </div>
      </div>
    )
  }
}

const LeftMenu = WithContext(LeftMenu_)

export default () => (
  <Row>
    <Col md="3">
      <LeftMenu/>
    </Col>
    <Col md="9">
      <Switch>
        <Route exact path="/" render={ListConversations}/>
        <Route exact path="/:flag(draft|sent|archive|all|spam|deleted)/" render={ListConversations}/>
        <Route exact path="/create/" render={CreateConversation}/>
        <Route path="/:key([a-f0-9]{10,64})/" render={ConversationDetails}/>
        <Route component={NotFound}/>
      </Switch>
    </Col>
  </Row>
)