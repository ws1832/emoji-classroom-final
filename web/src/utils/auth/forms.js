// 这里只校验确认密码一致；密码强度由后端统一强制执行。
export function samePassword(password, confirmation) {
  return typeof confirmation === 'string' && confirmation.length > 0 && password === confirmation
}

export function validEmail(value) {
  return typeof value === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())
}

export function studentRegistrationPayload({ username, email, password }) {
  return { username: username.trim(), email: email.trim(), password }
}

export function passwordPayload({ old_password, new_password }) {
  return { old_password, new_password }
}

export function clearLegacyPassword(storage) {
  try {
    const previous = storage.get('loginInfo')
    if (previous && typeof previous === 'object') {
      // Remove secrets before attempting a write, which can fail under storage quotas.
      storage.remove('loginInfo')
      if (typeof previous.username === 'string') {
        storage.set('loginInfo', { username: previous.username })
      }
    }
  } catch {
    // Inaccessible browser storage must not prevent the login UI from mounting.
    try {
      storage.remove('loginInfo')
    } catch {
      // The browser denied access; no new credentials are persisted.
    }
  }
}
