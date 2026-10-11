// Иллюстрация двора для карточки объявлений (из макета «Ваш дом сегодня»).
// Декор: aria-hidden, цвета — фиксированная мягкая палитра карточки, а не
// бренд-токены (на обоих брендах карточка одинаково зелёная).
// brand-allow — палитра иллюстрации не брендовая.

export default function CourtyardArt() {
  return (
    <svg className="rh-courtyard" viewBox="0 0 450 350" fill="none" aria-hidden="true" focusable="false">
      <defs>
        <pattern id="rh-windows" width="27" height="28" patternUnits="userSpaceOnUse">
          <rect x="7" y="5" width="10" height="14" rx="1" fill="#eaf4e3" stroke="#90b982" strokeWidth="1.2" />
        </pattern>
      </defs>
      <circle cx="300" cy="146" r="143" fill="#dfefd4" />
      <path d="M37 310H438M6 323h381" stroke="#8caf7c" strokeWidth="1.4" />
      <path d="M126 301V102l83-19v219" fill="#f6faef" stroke="#84ac74" strokeWidth="1.5" />
      <path d="M137 114h60v167h-60z" fill="url(#rh-windows)" />
      <path d="m122 102 87-20 34 17v203h-34V83" fill="#d6e9c9" stroke="#84ac74" strokeWidth="1.5" />
      <path d="m221 116 10 4v14l-10-3Zm0 29 10 3v14l-10-2Zm0 29 10 2v14l-10-1Zm0 29 10 1v14h-10Zm0 29h10v14l-10 1Zm0 29 10-1v14l-10 2Z" fill="#edf5e6" stroke="#95b886" strokeWidth="1.1" />
      <path d="M275 302V40l79-18v280" fill="#f5f9ed" stroke="#84ac74" strokeWidth="1.5" />
      <path d="m275 40 79-18 29 14v266h-29V22" fill="#d6e9c9" stroke="#84ac74" strokeWidth="1.5" />
      <path d="M286 54h58v220h-58z" fill="url(#rh-windows)" />
      <path d="m365 52 7 3v14l-7-2Zm0 31 7 2v14l-7-2Zm0 31 7 2v14l-7-2Zm0 31 7 2v14l-7-2Zm0 31 7 1v14h-7Zm0 31h7v14h-7Zm0 31h7v14h-7Zm0 31h7v14h-7Z" fill="#edf5e6" stroke="#95b886" />
      <path d="M255 302v-62h34v62m-21-48v27m10-27v27" stroke="#84ac74" strokeWidth="1.5" />
      <path d="M169 302v-23h18v23m121 0v-23h18v23" fill="#bdd8a9" stroke="#84ac74" strokeWidth="1.5" />
      <path d="M92 309v-75m0 26-25-17m25-1 19-17" stroke="#547d41" strokeWidth="2" />
      <path d="M87 172c-16 0-26 14-26 29-18 4-24 21-13 34-1 20 16 32 32 28 15 13 43 5 47-14 19-3 27-25 13-39 1-21-13-38-29-32-6-5-14-7-24-6Z" fill="#c1dfa5" stroke="#76a65c" strokeWidth="1.6" />
      <path d="M93 306v-81m0 31-18-16m18 0 18-16" stroke="#648b4e" strokeWidth="1.5" />
      <path d="M400 310v-88m0 30-19-15m19 0 15-17" stroke="#547d41" strokeWidth="2" />
      <path d="M398 170c-24 5-39 47-35 65 6 23 40 31 59 15 26-22 4-79-24-80Z" fill="#aacf8b" stroke="#76a65c" strokeWidth="1.6" />
      <path d="M400 307v-93m0 32-20-17m20-2 13-13" stroke="#648b4e" strokeWidth="1.5" />
      <path d="M206 294h53m-50-9h48m-44 0v23m40-23v23m-44-14v14" stroke="#62844f" strokeWidth="2.4" strokeLinecap="round" />
      <path d="M15 309c0-13 17-19 25-9 3-23 27-21 28 0 15-6 23 4 23 9M327 308c4-19 21-18 25-7 10-17 28-9 27 7" fill="#accf91" stroke="#80a569" strokeWidth="1.4" />
      <path d="M250 80c4-4 8-4 12 0 3-5 7-6 12-3m-213 46c4-4 8-4 12 0 3-5 7-6 12-3" stroke="#83a672" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M104 332h154m22 0h25m-192 10h81" stroke="#b1cba0" strokeWidth="1.3" />
    </svg>
  )
}
