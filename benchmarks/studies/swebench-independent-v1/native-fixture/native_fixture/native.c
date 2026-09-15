#include <Python.h>

static PyObject *answer(PyObject *self, PyObject *args) {
    return PyLong_FromLong(7);
}
static PyMethodDef methods[] = {
    {"answer", answer, METH_NOARGS, "Return the fixture witness."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_native", NULL, -1, methods};
PyMODINIT_FUNC PyInit__native(void) { return PyModule_Create(&module); }
