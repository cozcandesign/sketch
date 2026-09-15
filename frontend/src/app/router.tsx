import { createBrowserRouter, type RouteObject } from 'react-router'
import { Shell } from '@/app/layout/Shell'
import { DashboardPage } from '@/features/dashboard/DashboardPage'
import { CoinPage } from '@/features/coin/CoinPage'
import { NewsPage } from '@/features/news/NewsPage'
import { PredictionsPage } from '@/features/predictions/PredictionsPage'
import { CalibrationPage } from '@/features/calibration/CalibrationPage'
import { SettingsPage } from '@/features/settings/SettingsPage'
import { CostsPage } from '@/features/costs/CostsPage'

export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Shell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'coin/:symbol?', element: <CoinPage /> },
      { path: 'news', element: <NewsPage /> },
      { path: 'predictions', element: <PredictionsPage /> },
      { path: 'calibration', element: <CalibrationPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: 'costs', element: <CostsPage /> },
    ],
  },
]

export const router = createBrowserRouter(routes)
