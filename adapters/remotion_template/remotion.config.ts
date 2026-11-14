/**
 * Remotion bundler configuration.
 *
 * IMPORTANT:
 * Motion Studio and the Remotion adapter are installed as separate npm
 * projects. SceneWorld.tsx is shared by both projects, so without aliases
 * Rspack can bundle a second copy of React / React Three Fiber / Three from
 * motion_studio/node_modules. That splits the R3F Canvas context and causes:
 *
 *   R3F: Hooks can only be used within the Canvas component!
 *
 * Pin these imports to the adapter's dependency tree so ThreeCanvas and
 * SceneWorld use the exact same React + R3F + Three module instances.
 */
import path from "node:path";
import { Config } from "@remotion/cli/config";

const adapterNodeModules = path.resolve(process.cwd(), "node_modules");

const singletonAliases = {
  "react$": path.join(adapterNodeModules, "react"),
  "react/jsx-runtime$": path.join(adapterNodeModules, "react", "jsx-runtime.js"),
  "react/jsx-dev-runtime$": path.join(adapterNodeModules, "react", "jsx-dev-runtime.js"),
  "react-dom$": path.join(adapterNodeModules, "react-dom"),
  "react-dom/client$": path.join(adapterNodeModules, "react-dom", "client.js"),
  "@react-three/fiber$": path.join(adapterNodeModules, "@react-three", "fiber"),
  "@react-three/drei$": path.join(adapterNodeModules, "@react-three", "drei"),
  "three$": path.join(adapterNodeModules, "three"),
};

Config.setRspack(true);
Config.setChromiumOpenGlRenderer("angle");
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setDefaultPremountInSeconds(2);

Config.overrideRspackConfig((current) => ({
  ...current,
  resolve: {
    ...current.resolve,
    alias: {
      ...(current.resolve?.alias ?? {}),
      ...singletonAliases,
    },
  },
}));
