import moment from 'moment'

const DF = 'Do MMM'
const DFY = 'Do MMM YYYY'
const DTF = 'Do MMM, h:mma'

export const format_date = (ts, y) => moment(ts).format(y ? DFY : DF)
export const format_ts = ts => moment(ts).format(DTF)
