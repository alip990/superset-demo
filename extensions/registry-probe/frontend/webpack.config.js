// Matches the OFFICIAL 6.1.0 CLI template's public API bridge and host React.
const path = require('path');
const { ModuleFederationPlugin } = require('webpack').container;
const extension = require('../extension.json');
module.exports = {
  entry: {},
  output: {
    clean: true,
    path: path.resolve(__dirname, 'dist'),
    publicPath: `/api/v1/extensions/${extension.publisher}/${extension.name}/`,
    chunkFilename: '[name].[contenthash].js',
  },
  externalsType: 'window',
  externals: { '@apache-superset/core': 'superset' },
  plugins: [new ModuleFederationPlugin({
    name: 'jalaliLab_registryProbe',
    filename: 'remoteEntry.[contenthash].js',
    exposes: { './index': './src/index.tsx' },
    shared: {
      react: { singleton: true, eager: true, import: false, requiredVersion: '^17.0.2' },
      'react-dom': { singleton: true, eager: true, import: false, requiredVersion: '^17.0.2' },
    },
  })],
};
