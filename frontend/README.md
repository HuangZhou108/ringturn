# RingTurn 前端

## 前端概述

基于 AI 的音乐改编应用前端。用户可以通过上传音频文件，自然语言描述，输入时长、速度等参数，提出个性化的需求，系统将自动生成改编后的音乐。目前支持多轮对话，对话过程中实时显示进度。

## 环境要求

```
- Node.js ≥ 18.18.0
- npm ≥ 9
```

## 安装依赖

```
npm install
```

## 启动服务

```
npm run dev
```

浏览器访问 `http://localhost:5173/`

## 技术栈

| 类别      | 技术                       |
| --------- | -------------------------- |
| 框架      | React 19 + TypeScript      |
| 构建工具  | Vite 8                     |
| 路由      | React Router v7            |
| 国际化    | i18next + react-i18next    |
| 样式      | Tailwind CSS 3             |
| 动画      | Framer Motion              |
| HTTP 请求 | Fetch API                  |
| 代码规范  | ESLint + TypeScript ESLint |

## 项目结构

```
frontend/
├── public/ # 静态资源
├── src/
│ ├── api/
│ │ └── index.ts # API 请求封装
│ ├── components/ # 通用组件
│ ├── pages/
│ │ ├── Home.tsx # 首页
│ │ └── ChatFlow.tsx # 聊天页
│ ├── types/
│ │ └── index.ts # TypeScript 类型定义
│ ├── App.tsx # 路由配置
│ ├── main.tsx # 应用入口
│ ├── i18n.ts # 国际化配置
│ └── index.css # 全局样式（Tailwind）
├── index.html # HTML 入口
├── vite.config.ts # Vite 配置（含代理）
├── tailwind.config.js # Tailwind 配置
├── postcss.config.js # PostCSS 配置
├── tsconfig.json # TypeScript 配置
└── package.json # 项目依赖
```

## 页面路由

| 路径    | 页面     | 说明                                     |
| ------- | -------- | ---------------------------------------- |
| `/`     | Home     | 首页，输入需求、上传文件、设置参数       |
| `/chat` | ChatFlow | 聊天页，继续对话，展示对话历史和处理结果 |

## API接口

所有接口通过 `/api/v1` 前缀访问，返回统一格式：

```
{
  "code": 200,
  "data": {},
  "message": null
}
```

| 方法   | 路径                             | 说明               |
| :----- | :------------------------------- | :----------------- |
| POST   | `/api/v1/upload`                 | 上传音频文件       |
| POST   | `/api/v1/tasks`                  | 创建改编任务       |
| GET    | `/api/v1/tasks/{task_id}`        | 获取任务详情       |
| GET    | `/api/v1/tasks/{task_id}/status` | 获取任务状态       |
| GET    | `/api/v1/tasks/{task_id}/result` | 获取生成结果       |
| DELETE | `/api/v1/tasks/{task_id}`        | 取消任务           |
| GET    | `/api/v1/users/{user_id}/tasks`  | 获取历史任务列表   |
| GET    | `/static/ringtones/{file}`       | 下载生成的音频文件 |

## 国际化

支持中文和英文，通过页面右上角 Language 按钮切换。语言包配置在 `src/i18n.ts`。

## React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
