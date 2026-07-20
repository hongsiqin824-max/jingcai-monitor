import unittest
from unittest.mock import patch

import server


class SupportRateImageTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_build_figure_uses_all_csv_points_and_three_series(self):
        data = server.read_chart_data("2040566")
        self.assertIsNotNone(data)

        figure, meta = server.build_support_rate_figure("2040566")

        self.assertEqual((figure.layout.width, figure.layout.height), (1068, 860))
        self.assertEqual(len(figure.data), 3)
        self.assertTrue(all(len(trace.x) == len(data["times"]) for trace in figure.data))
        self.assertIn(meta["主队"], figure.layout.title.text)
        self.assertIn(meta["客队"], figure.layout.title.text)

    def test_image_route_rejects_an_invalid_match_id(self):
        response = self.client.get("/api/chart/not-a-number/image")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_match_id")

    def test_image_route_returns_not_found_for_missing_data(self):
        response = self.client.get("/api/chart/999999999/image")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "support_rate_not_found")

    @patch("server.render_support_rate_png")
    def test_image_route_returns_png_and_utf8_filename(self, render_png):
        render_png.return_value = (
            b"\x89PNG\r\n\x1a\ntest",
            "周一201_TPS图尔库VS坦佩雷山猫_支持率.png",
        )

        response = self.client.get("/api/chart/2040566/image")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "image/png")
        self.assertEqual(response.data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
