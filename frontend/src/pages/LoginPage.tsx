import React, { useState } from "react";
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  CircularProgress,
} from "@mui/material";
import axios from "axios";
import { useNavigate } from "react-router-dom";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

type FormState = {
  tenant_name: string;
  email: string;
  password: string;
};

export default function LoginPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>({
    tenant_name: "",
    email: "",
    password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.tenant_name || !form.email || !form.password) {
      setError("All fields are required.");
      return;
    }

    setLoading(true);

    try {
      const res = await axios.post(`${API_URL}/api/v1/auth/login`, form);
      // Store token in memory (can add context/global store if needed)
      window.localStorage.setItem("klaris_jwt", res.data.access_token);
      window.localStorage.setItem("klaris_user", JSON.stringify(res.data.user));
      window.localStorage.setItem("klaris_tenant", JSON.stringify(res.data.tenant));
      // Debug check
      console.log("LOGIN success, ls:", {
        jwt: window.localStorage.getItem("klaris_jwt"),
        user: window.localStorage.getItem("klaris_user"),
        tenant: window.localStorage.getItem("klaris_tenant")
      });
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      let msg =
        err?.response?.data?.detail ||
        "Login failed. Check your credentials and tenant name.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box mt={8}>
        <Card>
          <CardContent>
            <Typography variant="h5" gutterBottom>
              Login
            </Typography>
            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
            <form onSubmit={handleSubmit} noValidate>
              <TextField
                fullWidth
                margin="normal"
                label="Tenant Name"
                name="tenant_name"
                value={form.tenant_name}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Email"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Password"
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                required
              />
              <Box mt={2}>
                <Button
                  variant="contained"
                  color="primary"
                  type="submit"
                  fullWidth
                  disabled={loading}
                  size="large"
                  startIcon={loading ? <CircularProgress size={20} /> : null}
                >
                  {loading ? "Signing in..." : "Login"}
                </Button>
              </Box>
            </form>
            <Box mt={2} textAlign="center">
              <Button color="secondary" onClick={() => navigate("/register")}> 
                Need an account? Register
              </Button>
            </Box>
          </CardContent>
        </Card>
      </Box>
    </Container>
  );
}
