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

  // console.dir(config, { depth: 10, colors: true })
  return config
}
