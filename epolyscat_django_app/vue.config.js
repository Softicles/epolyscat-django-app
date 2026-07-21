const BundleTracker = require("webpack-bundle-tracker");

module.exports = {
  publicPath:
        process.env.NODE_ENV === "development"
          ? "http://0.0.0.0:9000/static/epolyscat_django_app/dashboard/dist/" : "/static/epolyscat_django_app/dashboard/dist/",
  // baseUrl: "http://0.0.0.0:8080/",
  outputDir: './static/epolyscat_django_app/dashboard/dist',

  // Keep lint findings non-fatal, as they were under Vue CLI 3. The stricter
  // eslint 8 / eslint-plugin-vue 9 defaults would otherwise fail the build on
  // pre-existing issues that are unrelated to the build toolchain.
  lintOnSave: 'warning',

  // webpack-dev-server v4 config. The old chainWebpack devServer chain
  // (public/hotOnly/https/disableHostCheck) was removed in v4.
  devServer: {
    host: '0.0.0.0',
    port: 9000,
    hot: 'only',
    allowedHosts: 'all',
    server: 'http',
    headers: {"Access-Control-Allow-Origin": "*"},
    client: {
      webSocketURL: 'ws://0.0.0.0:9000/ws',
    },
    static: {
      watch: {poll: 1000},
    },
  },
  css: {
    loaderOptions: {
      // postcss config is picked up from the "postcss" key in package.json;
      // postcss-loader 6+ no longer accepts an explicit config path.
      sass: {
        sassOptions: {
          // Turn off deprecation warnings for sass dependencies
          quietDeps: true,
        },
      },
    },
  },
  configureWebpack: {
    optimization: {
      /*
       * Force creating a vendor bundle so we can load the 'app' and 'vendor'
       * bundles on development as well as production using django-webpack-loader.
       * Otherwise there is no vendor bundle on development and we would need
       * some template logic to skip trying to load it.
       * See also: https://bitbucket.org/calidae/dejavu/src/d63d10b0030a951c3cafa6b574dad25b3bef3fe9/%7B%7Bcookiecutter.project_slug%7D%7D/frontend/vue.config.js?at=master&fileviewer=file-view-default#vue.config.js-27
       */
      splitChunks: {
        cacheGroups: {
          vendors: {
            name: 'chunk-vendors',
            test: /[\\/]node_modules[\\/]/,
            priority: -10,
            chunks: 'initial',
          },
        // there is only one entry point so common chunk isn't needed
        //   common: {
        //     name: 'chunk-common',
        //     minChunks: 2,
        //     priority: -20,
        //     chunks: 'initial',
        //     reuseExistingChunk: true
        //   }
        },
      },
    },
  },

  chainWebpack: config => {

    // webpack-bundle-tracker 1.0+ splits the old single `filename` path into
    // a directory (`path`) plus a bare `filename`.
    config
      .plugin('BundleTracker')
      .use(BundleTracker, [{
        path: './static/epolyscat_django_app/dashboard/dist',
        filename: 'webpack-stats.json',
      }]);

    config.resolve.alias
      .set('__STATIC__', 'static');
  },
};
