import axios from 'axios'

export const request = axios.create({
  baseURL: '/api/v1',
  timeout: 300_000,
})
