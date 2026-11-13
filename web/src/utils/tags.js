// Keep internal route identifiers stable, but refresh persisted display labels.
export function upsertRouteTag(tags, tag) {
  const index = tags.findIndex((item) => item.path === tag.path)
  if (index < 0) return [...tags, tag]
  const updated = [...tags]
  updated[index] = { ...tags[index], ...tag, title: tag.title || tags[index].title }
  return updated
}

// Layout + empty child routes describe the same page, not two breadcrumb levels.
export function routeBreadcrumbs(matched) {
  return matched.filter((item, index) => {
    if (!item.meta?.title) return false
    return !matched.slice(0, index).some(
      (previous) => previous.path === item.path && previous.meta?.title === item.meta.title
    )
  })
}
