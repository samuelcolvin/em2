/*
JS used when rendering html messages.
Note: this isn't run through webpack, babel etc. so needs to be "browser ready" javascript.
*/
function parent_send (data) {
  window.parent.postMessage(Object.assign(data, {iframe_id: parseInt(document.title)}), '*')
}

window.onload = function () {
  parent_send({height: Math.min(500, Math.max(50, document.documentElement.offsetHeight))})
  for (const link of document.links) {
    link.onclick = function (e) {
      e.preventDefault()
      parent_send({href: link.getAttribute('href')})
    }
  }
}
