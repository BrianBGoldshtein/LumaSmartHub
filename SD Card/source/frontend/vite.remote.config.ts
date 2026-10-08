import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {copyFile,mkdir,readdir,writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';
import {remoteIcon} from './tools/remote-icon.mjs';
export default defineConfig({
  root:'remote',base:'/remote/',publicDir:'public',plugins:[react(),{
    name:'legacy-updater-compatible-remote-assets',
    async closeBundle(){
      // Deployed 0.2.x accepts only frontend/index.html and flat assets/.
      // Keep a separate remote build, then copy its prefixed files into that
      // existing signed boundary. The gateway maps only remote-* resources.
      const source=resolve('remote-build'),target=resolve('dist/assets');
      await mkdir(target,{recursive:true});
      for(const name of await readdir(resolve(source,'assets'))){
        if(!/^remote-[A-Za-z0-9_-]+\.(js|css|woff2?|svg|png)$/.test(name))throw Error('Unexpected remote build asset.');
        await copyFile(resolve(source,'assets',name),resolve(target,name));
      }
      for(const name of ['index.html','manifest.webmanifest','icon.svg'])
        await copyFile(resolve(source,name),resolve(target,'remote-'+name));
      for(const [size,name] of [[180,'touch-icon'],[192,'icon-192'],[512,'icon-512']] as const)
        await writeFile(resolve(target,`remote-${name}.png`),remoteIcon(size));
    },
  }],
  build:{outDir:'../remote-build',emptyOutDir:true,target:'es2022',sourcemap:false,assetsInlineLimit:0,
    rolldownOptions:{output:{entryFileNames:'assets/remote-[name]-[hash].js',chunkFileNames:'assets/remote-[name]-[hash].js',assetFileNames:'assets/remote-[name]-[hash][extname]'}}},
});
