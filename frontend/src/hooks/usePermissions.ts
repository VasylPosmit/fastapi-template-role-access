import { type Permission, UsersService } from "@/client"
import useAuth from "./useAuth"

// Plain function, usable in route `beforeLoad` (no React context there).
export const hasPermission = async (permission: Permission) => {
  const { data: user } = await UsersService.readUserMe()
  return user.permissions.includes(permission)
}

const usePermissions = () => {
  const { user } = useAuth()

  const can = (permission: Permission) =>
    user?.permissions.includes(permission) ?? false

  return { can }
}

export default usePermissions
