import { render } from 'preact'
import './styles/variables.css'
import './index.css'
import App from './app'
import { initSidecarListener } from './lib/api'

// v2.1.0 Phase 0: Tauri sidecar 模式下注册事件监听
// PyWebView 模式下为 no-op
// 必须在 render 前 await,确保 sidecar-ready 事件监听已注册,
// 避免竞态条件导致端口/token 注入失败
async function bootstrap() {
  await initSidecarListener()
  render(<App />, document.getElementById('app')!)
}

bootstrap()
