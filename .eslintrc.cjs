/* eslint-env node */
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    project: './tsconfig.json' // required for type-aware rules
  },
  plugins: [
    '@typescript-eslint',
    'react',
    'react-hooks',
    'jsx-a11y',
    'import',
    'boundaries',
    'sonarjs'
  ],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended-type-checked',
    'plugin:react/recommended',
    'plugin:react-hooks/recommended',
    'plugin:jsx-a11y/recommended',
    'plugin:import/recommended',
    'plugin:boundaries/recommended'
  ],
  settings: {
    'import/resolver': { typescript: true },
    // Architecture elements (SoC)
    'boundaries/elements': [
      { type: 'app',      pattern: 'src/app/*' },
      { type: 'pages',    pattern: 'src/pages/*' },
      { type: 'features', pattern: 'src/features/*' },
      { type: 'entities', pattern: 'src/entities/*' },
      { type: 'shared',   pattern: 'src/shared/*' },
      { type: 'api',      pattern: 'src/shared/api/**' } // your generated API
    ]
  },
  rules: {
    // ===== File size cap =====
    'max-lines': ['error', { max: 500, skipBlankLines: true, skipComments: true }],

    // ===== KISS / DRY proxies =====
    'complexity': ['error', 15],                          // cyclomatic
    'sonarjs/cognitive-complexity': ['error', 15],        // cognitive complexity
    'sonarjs/no-duplicate-string': ['warn', { threshold: 3 }],

    // ===== Separation of concerns =====
    // Only import generated API via its public entrypoint
    'import/no-restricted-paths': ['error', {
      zones: [
        {
          target: './src/shared/api/generated',
          from: './src',
          except: ['./src/shared/api/index.ts'] // re-export barrel only
        }
      ]
    }],
    // Enforce entrypoints per “element”
    'boundaries/entry-point': ['error', {
      default: 'disallow',
      rules: [{ from: ['*'], allow: ['src/shared/api/index.ts'] }]
    }],
    'boundaries/no-unknown': 'error',

    // ===== No manual HTTP calls to Mastodon =====
    // Ban literal host calls via fetch / axios (string-literal URLs only)
    'no-restricted-syntax': [
      'error',
      {
        selector:
          "CallExpression[callee.name='fetch'][arguments.0.type='Literal'][arguments.0.value=/mastodon\\./i]",
        message: 'Do not call Mastodon directly. Use the backend API.'
      },
      {
        selector:
          "CallExpression[callee.object.name='axios'][callee.property.name=/^(get|post|put|delete|patch|head|options)$/][arguments.0.type='Literal'][arguments.0.value=/mastodon\\./i]",
        message: 'Do not call Mastodon directly. Use the backend API.'
      },
      {
        // axios({ url: 'https://mastodon...' })
        selector:
          "CallExpression[callee.name='axios'] ObjectExpression > Property[key.name='url'] Literal[value=/mastodon\\./i]",
        message: 'Do not call Mastodon directly. Use the backend API.'
      }
    ],

    // React specifics
    'react/react-in-jsx-scope': 'off'
  },
  overrides: [
    {
      files: ['**/__tests__/**', '**/*.test.*'],
      rules: {
        'max-lines': 'off',
        'complexity': 'off',
        'sonarjs/cognitive-complexity': 'off'
      }
    }
  ]
};
