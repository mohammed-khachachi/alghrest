import { defineConfig, globalIgnores } from "eslint/config";
import js from "@eslint/js";
import ts from "typescript-eslint";
import hooks from "eslint-plugin-react-hooks";
export default defineConfig([
 globalIgnores([".next/**", "content/**", "public/**", "next-env.d.ts"]),
 js.configs.recommended,
 ts.configs.recommended,
 { files:["**/*.{ts,tsx,mjs}"], languageOptions:{ globals:{console:"readonly",process:"readonly",URL:"readonly",window:"readonly",document:"readonly",requestAnimationFrame:"readonly",cancelAnimationFrame:"readonly"} } },
 { files:["**/*.{ts,tsx}"], plugins:{"react-hooks":hooks}, rules:{"react-hooks/rules-of-hooks":"error","react-hooks/exhaustive-deps":"warn"} }
]);
