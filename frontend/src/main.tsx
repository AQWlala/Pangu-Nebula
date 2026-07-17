import { render } from 'preact'
import './styles/variables.css'
import './index.css'
import App from './app'
import ErrorBoundary from './components/ErrorBoundary'
import { initSidecarListener } from './lib/api'
import { StoreProvider } from './lib/store'

// v2.1.0 Phase 0: Tauri sidecar 模式下注册事件监听
// PyWebView 模式下为 no-op
// 必须在 render 前 await,确保 sidecar-ready 事件监听已注册,
// 避免竞态条件导致端口/token 注入失败
async function bootstrap() {
  await initSidecarListener()
  // v2.3.0 Phase 3-B: 挂载全局 store (SSE 连接 + 7 类 state)
  // 必须在 App 外层,使 MemoryGraph / DAGCanvas / EvolutionPage 等都能通过 useGlobalState 订阅事件
  render(
    <ErrorBoundary>
      <StoreProvider>
        <App />
      </StoreProvider>
    </ErrorBoundary>,
    document.getElementById('app')!
  )
}

bootstrap()
