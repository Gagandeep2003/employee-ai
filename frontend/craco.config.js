// craco.config.js
const path = require("path");
require("dotenv").config();

module.exports = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
    configure: (webpackConfig) => {
      // Fewer watched directories -- faster rebuilds in local dev.
      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: [
          "**/node_modules/**",
          "**/.git/**",
          "**/build/**",
          "**/dist/**",
          "**/coverage/**",
          "**/public/**",
        ],
      };
      return webpackConfig;
    },
  },
  devServer: (devServerConfig) => ({
    ...devServerConfig,
    headers: {
      ...devServerConfig.headers,
      "Cross-Origin-Resource-Policy": "same-origin",
    },
  }),
};
