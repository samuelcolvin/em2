const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin

module.exports = function override(config, env) {
  // Add worker-loader by hijacking configuration for regular .js files.

  const babel_loader = config.module.rules[2].oneOf.find(
      rule => rule.loader && rule.loader.indexOf('babel-loader') !== -1
  )

  // copied partially from https://github.com/facebook/create-react-app/pull/5886
  const worker_loader = {
    test: /\/worker\/worker\.js$/,
    include: babel_loader.include,
    use: [
      require.resolve('worker-loader'),
      {
        loader: babel_loader.loader,
        options: babel_loader.options,
      }
    ]
  }
  config.module.rules.push(worker_loader)

  // if run with `ANALYSE=1 yarn build` create report.js size report
  if (env === 'production' && process.env.ANALYSE) {
    config.plugins.push(
      new BundleAnalyzerPlugin({
        analyzerMode: 'static',
        reportFilename: 'report.html',
      })
    )
  }


  // temporary fix for https://github.com/webpack/webpack/issues/6525
  config.output.globalObject = 'this'
  // temporary fix for https://github.com/webpack-contrib/worker-loader/issues/176
  config.optimization.noEmitOnErrors = false

  // console.dir(config, { depth: 10, colors: true })

  return config
}
