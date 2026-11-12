import fs from 'node:fs';
import path from 'node:path';
import { registerHooks } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
import ts from 'typescript';

const FRONTEND_DIR = path.dirname(fileURLToPath(import.meta.url));
const SRC_DIR = path.join(FRONTEND_DIR, 'src');

function resolveFileCandidate(basePath) {
  const candidates = [
    basePath,
    `${basePath}.ts`,
    `${basePath}.tsx`,
    `${basePath}.js`,
    `${basePath}.mjs`,
    path.join(basePath, 'index.ts'),
    path.join(basePath, 'index.tsx'),
    path.join(basePath, 'index.js'),
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }
  return null;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('@/')) {
      const target = path.join(SRC_DIR, specifier.slice(2));
      const resolved = resolveFileCandidate(target);
      if (resolved) {
        return {
          url: pathToFileURL(resolved).href,
          shortCircuit: true,
        };
      }
    }

    if ((specifier.startsWith('./') || specifier.startsWith('../')) && context.parentURL?.startsWith('file:')) {
      const parentPath = fileURLToPath(context.parentURL);
      if (!parentPath.includes(`${path.sep}node_modules${path.sep}`)) {
        const target = path.resolve(path.dirname(parentPath), specifier);
        const resolved = resolveFileCandidate(target);
        if (resolved) {
          return {
            url: pathToFileURL(resolved).href,
            shortCircuit: true,
          };
        }
      }
    }

    return nextResolve(specifier, context);
  },

  load(url, context, nextLoad) {
    if (url.startsWith('file:')) {
      const filePath = fileURLToPath(url);
      if (
        !filePath.includes(`${path.sep}node_modules${path.sep}`) &&
        (filePath.endsWith('.ts') || filePath.endsWith('.tsx'))
      ) {
        const source = fs.readFileSync(filePath, 'utf8');
        const transpiled = ts.transpileModule(source, {
          fileName: filePath,
          compilerOptions: {
            module: ts.ModuleKind.ESNext,
            target: ts.ScriptTarget.ES2022,
            jsx: ts.JsxEmit.ReactJSX,
            esModuleInterop: true,
            resolveJsonModule: true,
          },
        });
        return {
          format: 'module',
          source: transpiled.outputText,
          shortCircuit: true,
        };
      }
    }
    return nextLoad(url, context);
  },
});
