const engineeringTypeLabels: Readonly<Record<string, string>> = {
  BRIDGE: '桥梁',
  BUILDING: '房建',
  EXPRESSWAY: '高速公路',
  GENERAL_CONSTRUCTION: '工程施工',
  GEOLOGICAL_ENGINEERING: '地质工程',
  HIGHWAY: '公路',
  MUNICIPAL: '市政工程',
  PORT_WATERWAY: '港口航道',
  RAILWAY: '铁路',
  ROAD: '道路',
  TUNNEL: '隧道',
  WATER_CONSERVANCY: '水利工程',
}

const hazardTypeLabels: Readonly<Record<string, string>> = {
  BLASTING: '爆破事故',
  BRIDGE_ERECTION: '桥梁架设事故',
  COLLAPSE: '坍塌',
  CONFINED_SPACE: '有限空间事故',
  ELECTRIC_SHOCK: '触电',
  EXPLOSION: '爆炸',
  FALL_FROM_HEIGHT: '高处坠落',
  FIRE: '火灾',
  FLOOD_AND_EXTREME_WEATHER: '洪涝与极端天气',
  GEOLOGICAL_DISASTER: '地质灾害',
  LIFTING_INJURY: '起重伤害',
  MACHINERY_INJURY: '机械伤害',
  OBJECT_STRIKE: '物体打击',
  OTHER: '其他',
  POISONING_SUFFOCATION: '中毒和窒息',
  ROADBED_COLLAPSE: '路基塌陷',
  SCAFFOLD_FORMWORK: '脚手架与模板事故',
  SPECIAL_EQUIPMENT: '特种设备事故',
  TEMPORARY_STRUCTURE_FAILURE: '临时结构失效',
  TRAFFIC_SAFETY: '交通安全事故',
  TUNNEL_COLLAPSE: '隧道坍塌',
  UNKNOWN: '待核实',
  VEHICLE_INJURY: '车辆伤害',
  WATER_INRUSH_MUDFLOW: '突水突泥',
}

function controlledLabel(
  value: string | null | undefined,
  labels: Readonly<Record<string, string>>,
): string | null {
  if (!value) return null
  return labels[value] ?? value
}

export function safetyEngineeringLabel(value: string | null | undefined): string | null {
  return controlledLabel(value, engineeringTypeLabels)
}

export function safetyHazardLabel(value: string | null | undefined): string | null {
  return controlledLabel(value, hazardTypeLabels)
}
