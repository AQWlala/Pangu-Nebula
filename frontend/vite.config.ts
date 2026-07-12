import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// T4.10 前端 bundle 优化配置
export default defineConfig({
  plugins: [preact()],
  build: {
    outDir: 'dist',
    // 代码分割: 将第三方依赖单独打包,提升缓存命中率
    rollupOptions: {
      output: {
        manualChunks: {
          // Preact 核心单独打包
          'preact-vendor': ['preact', 'preact-router'],
        },
      },
    },
    // 启用 CSS 代码分割
    cssCodeSplit: true,
    // 资源内联阈值 (小于 4KB 的资源内联为 base64)
    assetsInlineLimit: 4096,
    // 启用 sourcemap (生产环境可用,便于调试)
    sourcemap: false,
    // 压缩配置
    minify: 'esbuild',
    // chunk 大小警告阈值 (KB)
    chunkSizeWarningLimit: 500,
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:7860',
        changeOrigin: true
      }
    }
  },
  // 依赖预构建优化
  optimizeDeps: {
    include: ['preact', 'preact-router'],
  },
})
