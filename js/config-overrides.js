const fs = require('fs')
const path = require('path')

module.exports = function override(config, env) {
  // if run with `ANALYSE=1 yarn build` create report.js size report
  if (env === 'production' && process.env.ANALYSE) {
    const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin
    config.plugins.push(
      new BundleAnalyzerPlugin({
        analyzerMode: 'static',
        reportFilename: 'report.html',
      })
    )
  }
  // very useful way of allowing quick local development of dependencies
  fs.readdirSync(path.resolve(__dirname, 'src/extra_modules')).forEach(function (d) {
    config.resolve.alias[d] = path.resolve(__dirname, 'src/extra_modules/', d, 'src')
  })
  // console.dir(config, { depth: 10, colors: true })
  return config
}
