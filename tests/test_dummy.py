import unittest

from qgis.testing import start_app, stop_app, TestCase

app = start_app(True)

class MyTestCase(TestCase):
    def test_something(self):
        self.assertEqual(True, True)


if __name__ == '__main__':
    unittest.main()

#stop_app()