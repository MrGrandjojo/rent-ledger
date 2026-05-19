import axios from 'axios'

// 401 handling: AuthContext sets user=null on failure and RequireAuth in
// App.jsx triggers the redirect through React Router. A hard
// window.location.href redirect would loop because AuthContext re-runs
// /auth/me on every mount.
const api = axios.create({
  baseURL: '/rental/api',
  withCredentials: true,
})

export default api
