/// <reference types="vitest" />
import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// T4.10 前端 bundle 优化配置
// v2.1.0 Phase 0: Tauri 2 兼容 — base 路径 + strictPort + 环境检测
export default defineConfig({
  plugins: [preact()],
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
  // Tauri 2 打包后从 tauri:// 协议加载,需相对路径;dev 模式用绝对路径
  base: process.env.TAURI_ENV_PLATFORM ? './' : '/',
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
    // Tauri 2 devUrl 固定指向 localhost:5173,必须 strictPort 防止 Vite 换端口
    strictPort: true,
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
