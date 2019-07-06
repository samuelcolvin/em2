import React from 'react'
import {Link, Route, Switch} from 'react-router-dom'
import {ListGroup, DropdownItem, ListGroupItem as BsListGroupItem} from 'reactstrap'
import {FontAwesomeIcon} from '@fortawesome/react-fontawesome'
import * as fas from '@fortawesome/free-solid-svg-icons'
import {Error, NotFound, WithContext, as_title} from 'reactstrap-toolbox'
import ListConversations from './conversations/List'
import SearchResults from './conversations/SearchResults'
import ConversationDetails from './conversations/Details'
import CreateConversation from './conversations/Create'
import Wait from './conversations/Wait'

const ListGroupItem = ({className, to, active, icon, title, count, count_unseen}) => (
  <BsListGroupItem tag={Link} to={to} action active={active} className={className}>
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

  async componentDidMount () {
    this.mounted = true
    const state = await window.logic.conversations.update_counts()
    if (this.mounted) {
      this.setState(state)
      this.remove_listener = window.logic.add_listener('flag-change', counts => this.setState(counts))
    }
  }

  componentWillUnmount () {
    this.mounted = false
    this.remove_listener && this.remove_listener()
  }

  render () {
    const s = this.props.ctx.menu_item
    return (
      <div>
        <div className="box no-pad">
          <ListGroup>
            <ListGroupItem
              className="border-0"
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

// needs to match $grid-breakpoints: md
const menu_position_switch = 768

const TopMenuItem = ({to, active, icon, title, count, count_unseen}) => (
  <DropdownItem tag={Link} to={to} active={active}>
    <div className="d-flex justify-content-between py-2">
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
  </DropdownItem>
)

class TopMainMenu_ extends React.Component {
  state = {flags: {}, visible: false}

  async componentDidMount () {
    this.mounted = true
    const state = await window.logic.conversations.update_counts()
    if (this.mounted) {
      this.setState(state)
      this.logic_listener = window.logic.add_listener('flag-change', counts => this.setState(counts))
      this.resize_listener = window.addEventListener('resize', this.set_visible)
      setTimeout(() => this.set_visible(), 50)
    }
  }

  componentWillUnmount () {
    this.mounted = false
    this.logic_listener && this.logic_listener()
    this.resize_listener && this.resize_listener()
  }

  set_visible = () => {
    if (this.mounted) {
      const width = document.getElementById('main').offsetWidth
      this.setState({visible: width <= menu_position_switch})
    }
  }

  render () {
    if (this.state.visible) {
      return [
        <TopMenuItem
          key="create"
          to="/create/"
          active={this.props.ctx.menu_item === 'create'}
          icon={fas.faKeyboard}
          title="Compose"
        />,
        <DropdownItem key="divider1" divider/>,
        ...main_menu_items.map(m => (
          <TopMenuItem
            key={m.to}
            to={m.to}
            active={this.props.ctx.menu_item === m.name}
            icon={m.icon}
            title={as_title(m.name)}
            count={this.state.flags[m.name]}
            count_unseen={m.unseen && this.state.flags['unseen']}
          />
        )),
        <DropdownItem key="divider2" divider/>,
      ]
    } else {
      return null
    }
  }
}
export const TopMainMenu = WithContext(TopMainMenu_)


const WithMenu = ({children}) => {
  const ref_left = React.createRef()
  const ref_menu = React.createRef()

  const set_width = () => {
    const width = document.getElementById('main').offsetWidth
    if (width <= menu_position_switch) {
      ref_left.current.style.display = 'none'
    } else {
      ref_left.current.style.display = 'block'
      ref_menu.current.style.width = width / 4 - 30 + 'px'
    }
  }

  React.useEffect(() => {
    window.addEventListener('resize', set_width)
    setTimeout(() => ref_menu.current && set_width(), 0)
    return () => window.removeEventListener('resize', set_width)
  })
  return (
    <div className="with-menu">
      <div ref={ref_left} className="left-menu" style={{display: 'none'}}>
        <div ref={ref_menu} className="left-menu-fixed">
          <LeftMenu/>
        </div>
      </div>
      <div className="beside-menu">
        {children}
      </div>
    </div>
  )
}

// prompt new component construction when the key conv key changes
const render_conv_details = ({match}) => <ConversationDetails key={match.params.key}/>

export const RoutesWithMenu = () => (
  <WithMenu key="with-menu">
    <Switch>
      <Route exact path="/" component={ListConversations}/>
      <Route exact path="/:flag(draft|sent|archive|all|spam|deleted)/" component={ListConversations}/>
      <Route exact path="/search/" component={SearchResults}/>
      <Route exact path="/create/" component={CreateConversation}/>
      <Route path="/:key([a-f0-9]{10,64})/" render={render_conv_details}/>
      <Route path="/wait/:key([a-f0-9]{10,64})/" component={Wait}/>
      <Route component={NotFound}/>
    </Switch>
  </WithMenu>
)

export const ErrorWithMenu = ({error}) => (
  <WithMenu key="with-menu">
    <Error className="box" error={error}/>
  </WithMenu>
)
