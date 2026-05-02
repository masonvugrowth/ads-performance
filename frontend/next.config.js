/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  async redirects() {
    return [
      // /country was the old "Country Dashboard" route. The merged ADS
      // Performance dashboard at / now accepts the same query params
      // (country, branches, platform, funnel, range, campaign) so deep links
      // from Meta recommendations keep working.
      { source: '/country', destination: '/', permanent: false },
    ]
  },
}

module.exports = nextConfig
