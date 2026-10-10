import tseslint from "@typescript-eslint/eslint-plugin";
import parser from "@typescript-eslint/parser";

export default [{
  files: ["src/**/*.ts"],
  languageOptions: {
    parser,
    parserOptions: { project: "./tsconfig.json", tsconfigRootDir: import.meta.dirname }
  },
  plugins: { "@typescript-eslint": tseslint },
  rules: {
    "@typescript-eslint/no-explicit-any": "error",
    "@typescript-eslint/no-unsafe-assignment": "error",
    "@typescript-eslint/no-unsafe-argument": "error",
    "@typescript-eslint/no-unsafe-call": "error",
    "@typescript-eslint/no-unsafe-member-access": "error",
    "@typescript-eslint/no-unsafe-return": "error",
    "no-restricted-syntax": ["error", { selector: "TSEnumDeclaration", message: "Use literal unions." }]
  }
}];
