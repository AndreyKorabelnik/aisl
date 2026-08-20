import {cp, mkdir, rm, readFile, writeFile} from 'node:fs/promises';
import {resolve, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..');
const sdkRoot = resolve(process.env.AISL_SDK_TYPESCRIPT_ROOT || resolve(root, '../../packages/aisl-sdk-typescript'));
const src = resolve(sdkRoot, 'dist');
const dst = resolve(root, 'public/vendor/aisl-sdk');
await rm(dst, {recursive:true, force:true});
await mkdir(dst, {recursive:true});
await cp(src, dst, {recursive:true});
const version = (await readFile(resolve(sdkRoot,'VERSION'),'utf8')).trim();
await writeFile(resolve(dst,'VENDORED_FROM.txt'), `aisl-sdk-typescript ${version}\n`, 'utf8');
console.log(`vendored aisl-sdk-typescript ${version} from ${src}`);
