// src/components/Sidebar.tsx
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import type { TaskListItem } from '../types';

interface SidebarProps {
    sidebarOpen: boolean;
    setSidebarOpen: (open: boolean) => void;
    recentTasks: TaskListItem[];
    currentTaskId: string | null;
    setCurrentTaskId: (id: string | null) => void;
    onRefresh: () => Promise<void>;   // 刷新历史任务的方法
}

export default function Sidebar({
                                    sidebarOpen,
                                    setSidebarOpen,
                                    recentTasks,
                                    currentTaskId,
                                    setCurrentTaskId,
                                    onRefresh,
                                }: SidebarProps) {
    const { t } = useTranslation();
    const navigate = useNavigate();

    return (
        <aside
            className={`border-r border-[#e0f2fe] flex flex-col bg-[#f0f9ff] transition-all duration-300 ${
                sidebarOpen ? 'w-64 p-4' : 'w-0 p-0 overflow-hidden border-r-0'
            }`}
        >
            {/* Logo 区域 */}
            <div className="w-full mb-6">
                <div className="flex flex-row-reverse items-center justify-end gap-3">
                    {/* 收缩按钮 */}
                    <button
                        onClick={() => setSidebarOpen(!sidebarOpen)}
                        className="w-6 h-6 rounded hover:bg-gray-200 flex items-center justify-center flex-shrink-0 text-gray-400 hover:text-gray-600 transition"
                    >
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            {sidebarOpen ? (
                                <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            ) : (
                                <path d="M6 12L10 8L6 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            )}
                        </svg>
                    </button>
                    <div className="relative w-[132px] h-[38px]">
                        <div className="absolute left-0 -top-[1px]">
              <span className="text-lg font-semibold leading-tight text-[#0c4a6e] font-['Inter']">
                {t('sidebar.ringTurn')}
              </span>
                        </div>
                        <div className="absolute left-0 top-[22.5px]">
              <span className="text-[10px] font-semibold uppercase tracking-[1px] text-[#41565f]/70 font-['Inter']">
                {t('sidebar.aiMusic')}
              </span>
                        </div>
                    </div>
                    <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center flex-shrink-0">
                        <svg width="12" height="18" viewBox="0 0 12 18" fill="none">
                            <path d="M4 18C2.8999 18 1.9585 17.6083 1.17505 16.825C0.391602 16.0417 0 15.1 0 14C0 12.9 0.391602 11.9583 1.17505 11.175C1.9585 10.3917 2.8999 10 4 10C4.3833 10 4.73755 10.0458 5.0625 10.1375C5.38745 10.2292 5.69995 10.3667 6 10.55V0H12V4H8V14C8 15.1 7.6084 16.0417 6.82495 16.825C6.0415 17.6083 5.1001 18 4 18Z" fill="#458ecb"/>
                        </svg>
                    </div>
                </div>
            </div>

            {/* 新建 Adaptation 按钮 */}
            <button
                onClick={() => navigate('/')}
                className="w-[227px] self-stretch mb-6 px-4 py-3 bg-[#00639d] text-[#f7f9ff] rounded-xl hover:bg-[#005288] transition flex flex-row-reverse items-center justify-center gap-2"
            >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M6 7H0V5H6V0H8V5H14V7H8V14H6V7Z" fill="#f7f9ff"/>
                </svg>
                {t('sidebar.newAdaptation')}
            </button>

            {/* 静态主菜单 */}
            <div className="flex-1">
                <h2 className="text-xs uppercase tracking-wider text-gray-500 mb-3 flex items-center justify-between">
                    {t('sidebar.mainMenu')}
                    <button
                        onClick={onRefresh}
                        className="p-1 hover:bg-gray-200 rounded transition"
                        title={t('sidebar.refresh') || '刷新'}
                    >
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M12.8 5.6C12.4167 3.76667 11.325 2.2 9.525 1H11.9V0H7.9V4H9.3V2.475C9.8835 2.79167 10.35 3.25417 10.7 3.8625C11.05 4.47083 11.1667 5.13333 11.05 5.85C10.7167 7.65 9.33333 9.075 7 9.125C6.03333 9.15833 5.13333 8.86667 4.3 8.25C3.46667 7.63333 2.9 6.8 2.6 5.75H4.65C4.83333 6.35 5.175 6.84167 5.675 7.225C6.175 7.60833 6.75 7.8 7.4 7.8C8.4 7.8 9.20833 7.46667 9.825 6.8C10.4417 6.13333 10.675 5.33333 10.525 4.4L12.8 5.6Z" fill="#475569"/>
                        </svg>
                    </button>
                </h2>
                <ul className="space-y-1">
                    <li className="px-4 py-2.5 rounded-lg bg-white text-[#0369a1] cursor-pointer flex items-center gap-3 shadow-[0px_1px_2px_0px_#0000000D]">
                        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                            <path d="M9 18C6.69995 18 4.6958 17.2375 2.98755 15.7125C1.2793 14.1875 0.300049 12.2833 0.0500488 10H2.1001C2.3335 11.7333 3.104 13.1667 4.4126 14.3C5.7207 15.4333 7.25 16 9 16C10.95 16 12.6042 15.3208 13.9624 13.9625C15.3208 12.6042 16 10.95 16 9C16 7.05 15.3208 5.39587 13.9624 4.03748C12.6042 2.6792 10.95 2 9 2C7.8501 2 6.7749 2.26672 5.7749 2.80005C4.7749 3.33337 3.93335 4.06665 3.25 5H6V7H0V1H2V3.34998C2.8501 2.28333 3.88745 1.45837 5.11255 0.875C6.3374 0.291626 7.6333 0 9 0C10.25 0 11.4209 0.237549 12.5125 0.712524C13.6042 1.1875 14.5542 1.82922 15.3625 2.63745C16.1709 3.4458 16.8125 4.39587 17.2876 5.48755C17.7625 6.57922 18 7.75 18 9C18 10.25 17.7625 11.4208 17.2876 12.5125C16.8125 13.6042 16.1709 14.5542 15.3625 15.3625C14.5542 16.1708 13.6042 16.8125 12.5125 17.2875C11.4209 17.7625 10.25 18 9 18ZM11.8 13.2L8 9.40002V4H10V8.59998L13.2 11.8L11.8 13.2Z" fill="#0369a1"/>
                        </svg>
                        <span className="text-base font-normal">{t('sidebar.recentTracks')}</span>
                    </li>
                    <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path d="M10.5 13C11.2 13 11.7917 12.7583 12.2749 12.275C12.7583 11.7917 13 11.2 13 10.5V5H16V3H12V8.5C11.7832 8.33337 11.55 8.20837 11.3 8.125C11.05 8.04163 10.7832 8 10.5 8C9.80005 8 9.2085 8.2417 8.7251 8.72498C8.2417 9.20837 8 9.80005 8 10.5C8 11.2 8.2417 11.7917 8.7251 12.275C9.2085 12.7583 9.80005 13 10.5 13ZM6 16C5.44995 16 4.979 15.8042 4.5874 15.4125C4.1958 15.0208 4 14.55 4 14V2C4 1.44995 4.1958 0.979126 4.5874 0.587524C4.979 0.195801 5.44995 0 6 0H18C18.55 0 19.0208 0.195801 19.4126 0.587524C19.8042 0.979126 20 1.44995 20 2V14C20 14.55 19.8042 15.0208 19.4126 15.4125C19.0208 15.8042 18.55 16 18 16H6ZM6 14H18V14V14V2H18V2V2H6V2V2V2V14V14V14V14ZM2 20C1.44995 20 0.979004 19.8042 0.587402 19.4125C0.195801 19.0208 0 18.55 0 18V4H2V18V18V18H16V20H2ZM6 2V2V2V2V14V14V14V14V14V14V2V2V2V2Z" fill="#475569"/>
                        </svg>
                        {t('sidebar.library')}
                    </li>
                    <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                        <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
                            <path d="M0.800049 5C0.550049 4.71667 0.354004 4.40833 0.212402 4.07495C0.0708008 3.7417 0 3.3833 0 3C0 2.16663 0.291504 1.45837 0.875 0.875C1.4585 0.291626 2.1665 0 3 0C3.8335 0 4.5415 0.291626 5.125 0.875C5.7085 1.45837 6 2.16663 6 3C6 3.3833 5.9292 3.7417 5.7876 4.07495C5.646 4.40833 5.44995 4.71667 5.19995 5H0.800049ZM6 20C4.8999 20 3.9585 19.6083 3.17505 18.825C2.3916 18.0417 2 17.1 2 16H1L0 6H6L5 16H4C4 16.55 4.1958 17.0208 4.5874 17.4125C4.979 17.8042 5.44995 18 6 18C6.55005 18 7.021 17.8042 7.4126 17.4125C7.8042 17.0208 8 16.55 8 16V4C8 2.90002 8.3916 1.95837 9.17505 1.17505C9.9585 0.391724 10.8999 0 12 0C13.1001 0 14.0417 0.391724 14.825 1.17505C15.6084 1.95837 16 2.90002 16 4V20H14V4C14 3.44995 13.8042 2.97913 13.4126 2.58752C13.0208 2.1958 12.55 2 12 2C11.45 2 10.9792 2.1958 10.5874 2.58752C10.1958 2.97913 10 3.44995 10 4V16C10 17.1 9.6084 18.0417 8.82495 18.825C8.0415 19.6083 7.1001 20 6 20ZM2.80005 14H3.19995L3.80005 8H2.19995L2.80005 14ZM3.19995 8H2.80005L2.19995 8H3.80005L3.19995 8Z" fill="#475569"/>
                        </svg>
                        {t('sidebar.studioSessions')}
                    </li>
                    <li className="px-3 py-2 rounded-lg hover:bg-gray-100 text-gray-700 cursor-pointer flex items-center gap-2">
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                            <path d="M3 20C2.44995 20 1.979 19.8042 1.5874 19.4125C1.1958 19.0208 1 18.55 1 18V6.72498C0.699951 6.54163 0.458496 6.3042 0.274902 6.01245C0.0917969 5.72083 0 5.3833 0 5V2C0 1.44995 0.195801 0.979126 0.587402 0.587524C0.979004 0.195801 1.44995 0 2 0H18C18.55 0 19.0208 0.195801 19.4126 0.587524C19.8042 0.979126 20 1.44995 20 2V5C20 5.3833 19.9082 5.72083 19.7251 6.01245C19.5417 6.3042 19.3 6.54163 19 6.72498V18C19 18.55 18.8042 19.0208 18.4126 19.4125C18.0208 19.8042 17.55 20 17 20H3ZM3 7V18V18V18H17V18V18V18V7H3ZM2 5H18V5V5V2V2V2H2V2V2V2V5V5V5V5ZM7 12H13V10H7V12Z" fill="#475569"/>
                        </svg>
                        {t('sidebar.archive')}
                    </li>
                </ul>
            </div>

            {/* 底部设置 */}
            <div className="pt-4 border-t border-gray-200 space-y-2">
                <div className="px-3 py-2 text-gray-500 hover:text-blue-600 cursor-pointer flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.003-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                    </svg>
                    {t('sidebar.settings')}
                </div>
                <div className="px-3 py-2 text-gray-500 hover:text-blue-600 cursor-pointer flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 5.25h.008v.008H12v-.008Z" />
                    </svg>
                    {t('sidebar.support')}
                </div>
            </div>
        </aside>
    );
}
