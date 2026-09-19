import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 300_000,
})
