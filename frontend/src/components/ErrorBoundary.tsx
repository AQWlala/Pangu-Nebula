// Preact ErrorBoundary — 捕获子组件渲染错误,避免全局白屏
// Preact 无内置 ErrorBoundary,需用 class component 实现 componentDidCatch

import { Component } from 'preact'

interface Props {
  children: preact.ComponentChildren
}

interface State {
  hasError: boolean
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: preact.ErrorInfo) {
    // 记录到 localStorage 供诊断 (无 DevTools 时可查看)
    try {
      const log = {
        timestamp: new Date().toISOString(),
        message: error.message,
        stack: error.stack,
        componentStack: errorInfo.componentStack,
      }
      const existing = JSON.parse(localStorage.getItem('error-log') || '[]')
      existing.push(log)
      // 保留最近 20 条
      if (existing.length > 20) existing.shift()
      localStorage.setItem('error-log', JSON.stringify(existing))
    } catch {
      // localStorage 不可用时忽略
    }
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            padding: '24px',
            background: 'var(--bg-primary, #FFF8F0)',
            color: 'var(--text-primary, #8B4513)',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: '48px', marginBottom: '16px' }}>😵</div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>
            页面渲染出错
          </h2>
          <p style={{ fontSize: '14px', color: 'var(--text-secondary, #A0522D)', marginBottom: '16px' }}>
            {this.state.error?.message || '未知错误'}
          </p>
          {this.state.error?.stack && (
            <details
              style={{
                maxWidth: '600px',
                width: '100%',
                marginBottom: '16px',
                padding: '12px',
                background: 'var(--bg-card, #fff)',
                borderRadius: '8px',
                fontSize: '11px',
                textAlign: 'left',
              }}
            >
              <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
                错误堆栈
              </summary>
              <pre
                style={{
                  marginTop: '8px',
                  overflow: 'auto',
                  maxHeight: '200px',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {this.state.error.stack}
              </pre>
            </details>
          )}
          <button
            onClick={this.handleReset}
            style={{
              padding: '10px 24px',
              borderRadius: '8px',
              background: 'var(--accent, #FF8C42)',
              color: '#fff',
              border: 'none',
              cursor: 'pointer',
              fontSize: '14px',
              fontWeight: 600,
            }}
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
