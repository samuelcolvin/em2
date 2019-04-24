module.exports = {
  root: true,
  parser: 'babel-eslint',
  parserOptions: {
    sourceType: 'module',
    ecmaFeatures: {
      'jsx': true
    },
  },
  globals: {
    enz: true,
    xhr_calls: true,
  },
  plugins: [
    'react'
  ],
  extends: 'react-app',
  rules: {
    'semi': [2, 'never'],
    // allow paren-less arrow functions
    'arrow-parens': 0,
    'generator-star-spacing': [2, 'after'],
    // allow debugger during development
    'no-debugger': 2,
    'object-curly-spacing': 2,
    'comma-dangle': [2, 'always-multiline'],
    'camelcase': 0,
    'no-alert': 2,
    'space-before-function-paren': 2,
    'react/jsx-uses-react': 2,
    'react/jsx-uses-vars': 2,
    'no-unused-vars': 2,
    'react-hooks/rules-of-hooks': 2,
    'react-hooks/exhaustive-deps': 2,
    'max-len': [
      'error', {
        'code': 120
    }]
  }
}
