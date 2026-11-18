/**
 * Tailwind CSS v3 build for SCMS-AI (same version line the Tailwind Play CDN used).
 * Run `npm run build:css` after changing classes in a template or a static script,
 * and commit app/static/css/tailwind.css: the app and the Docker image only serve the built file.
 */
module.exports = {
  content: [
    "./app/views/templates/**/*.html",
    "./app/static/js/**/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
