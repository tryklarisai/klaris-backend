import React, { useState } from "react";
import {
  Container,
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  MenuItem,
  Alert,
  CircularProgress,
} from "@mui/material";
import axios from "axios";
import { useNavigate } from "react-router-dom";

const plans = [
  { value: "pilot", label: "Pilot" },
  { value: "pro", label: "Pro" },
  { value: "enterprise", label: "Enterprise" },
];

// Helper: password validation
const isPasswordValid = (password: string) =>
  /^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$/.test(password);

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

type FormState = {
  name: string;
  plan: string;
  root_user_name: string;
  root_user_email: string;
  root_user_password: string;
};

export default function RegisterPage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<FormState>({
    name: "",
    plan: "",
    root_user_name: "",
    root_user_email: "",
    root_user_password: "",
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Basic validation
    if (
      !form.name ||
      !form.plan ||
      !form.root_user_name ||
      !form.root_user_email ||
      !form.root_user_password
    ) {
      setError("All fields are required.");
      return;
    }
    if (!isPasswordValid(form.root_user_password)) {
      setError(
        "Password must be at least 8 characters, include one letter, one number, and one symbol."
      );
      return;
    }

    setLoading(true);

    try {
      const res = await axios.post(`${API_URL}/api/v1/tenants/`, {
        ...form,
        credit_balance: 0, // hidden; default
        settings: {}, // hidden; default
      });
      setSuccess(res.data);
    } catch (err: any) {
      let msg =
        err?.response?.data?.detail ||
        "Failed to register. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <Container maxWidth="sm">
        <Box mt={8}>
          <Card>
            <CardContent>
              <Typography variant="h5" gutterBottom>
                Tenant Registered!
              </Typography>
              <Typography>
                <b>Tenant:</b> {success.name}
              </Typography>
              <Typography>
                <b>Root User Email:</b> {success.root_user.email}
              </Typography>
              <Box mt={2}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={() => navigate("/login")}
                >
                  Go to Login
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="sm">
      <Box mt={8}>
        <Card>
          <CardContent>
            <Typography variant="h5" gutterBottom>
              Register Tenant (Pilot Demo)
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
                name="name"
                value={form.name}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                select
                margin="normal"
                label="Plan"
                name="plan"
                value={form.plan}
                onChange={handleChange}
                required
              >
                {plans.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                fullWidth
                margin="normal"
                label="Root User Name"
                name="root_user_name"
                value={form.root_user_name}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Root User Email"
                name="root_user_email"
                type="email"
                value={form.root_user_email}
                onChange={handleChange}
                required
              />
              <TextField
                fullWidth
                margin="normal"
                label="Root User Password"
                name="root_user_password"
                type="password"
                value={form.root_user_password}
                onChange={handleChange}
                required
                helperText="Min. 8 characters, at least one letter, number, and symbol."
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
                  {loading ? "Registering..." : "Register Tenant"}
                </Button>
              </Box>
            </form>
          </CardContent>
        </Card>
        <Box mt={2} textAlign="center">
          <Button color="secondary" onClick={() => navigate("/login")}> 
            Already have an account? Login
          </Button>
        </Box>
      </Box>
    </Container>
  );
}
