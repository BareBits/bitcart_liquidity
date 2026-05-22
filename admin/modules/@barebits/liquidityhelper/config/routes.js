// Registers /liquidityhelper with bitcart's Nuxt router.
//
// Single-segment path: Nuxt 2.15's `getLocation` helper does
// `base.slice(0, -1)` on the configured router base, which corrupts a
// no-trailing-slash base like "/admin" → "/admi" and then trims that
// off the incoming path. With a single-segment route (e.g. `/admin/
// liquidityhelper`) the matcher still finds the route in the eventual
// re-resolve pass, but with a deeper path like `/admin/plugins/
// liquidityhelper` it doesn't — first paint 404s on a fresh load.
// Keep this path one segment deep to sidestep that whole class of bug
// without patching bitcart-admin.
//
// CRITICAL: the dynamic `import()` must be unwrapped via `.then(m =>
// m.default || m)`. ES dynamic imports resolve to the entire module
// namespace object — `{ default: Component, ...named }` — not the
// component object itself. Vue Router 3 has internal handling for
// this case but bitcart's setup (Nuxt 2.15 + vuems-injected routes,
// NOT Nuxt's auto-routing) hits a code path where the namespace
// wrapper reaches the SSR renderer and is treated as an anonymous
// component definition. That fails with the unhelpful error
// "render function or template not defined in component: anonymous"
// when an authenticated user actually loads the page.
//
// Nuxt's auto-routing solves this with an `interopDefault()` helper
// (see /src/.nuxt/defaultRouter.js) that wraps every page import.
// Vuems doesn't apply it, so we have to inline the same unwrap here.
//
// The @LiquidityHelper alias resolves to this module's root (see
// config/index.js), so the path below ends up at
// /src/modules/@barebits/liquidityhelper/pages/index.vue.
export default [
  {
    name: "liquidityhelper-plugin",
    path: "/liquidityhelper",
    component: () =>
      import("@LiquidityHelper/pages/index.vue").then((m) => m.default || m),
  },
]
